"""Gateway Manager — the Facade over all payment providers.

This is the single seam the payment/refund services use to reach any provider.
Responsibilities:

* Resolve a tenant's provider credentials, decrypting them from the vault.
* Instantiate the correct adapter via the plugin registry (Factory).
* Wrap every outbound call in resilience (retry + circuit breaker) and record
  metrics, so business services never deal with transport concerns.

The manager is a process-level singleton (one shared HTTP client and one set of
circuit breakers per provider) created at application startup.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from app.core.config import Settings
from app.core.errors import NotFoundError, ProviderError, ProviderUnavailableError
from app.core.metrics import provider_call_duration_seconds, provider_calls_total
from app.core.resilience import CircuitBreaker, RetryPolicy, retry_async
from app.domain.enums import ProviderName
from app.providers.base import BasePaymentProvider, ProviderContext
from app.providers.registry import build_provider
from app.repositories.audit import ProviderConfigRepository
from app.security.crypto import SecretBox

T = TypeVar("T")

# Default sandbox signing secret for the built-in mock provider when a tenant has
# not configured explicit credentials. Non-secret by design (sandbox only).
_MOCK_SANDBOX_SECRET = "upgi_sandbox_signing_secret"  # noqa: S105 - sandbox-only, non-sensitive


class GatewayManager:
    def __init__(
        self,
        *,
        settings: Settings,
        secret_box: SecretBox,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._secret_box = secret_box
        self._http = http_client
        self._breakers: dict[ProviderName, CircuitBreaker] = {}

    # -- Provider resolution ---------------------------------------------------
    async def get_provider(
        self,
        config_repo: ProviderConfigRepository,
        owner_id: uuid.UUID,
        provider: ProviderName,
    ) -> BasePaymentProvider:
        config = await config_repo.get_active(owner_id, provider)
        if config is not None:
            secret = self._secret_box.decrypt(config.encrypted_secret, aad=str(owner_id))
            context = ProviderContext(
                secret=secret,
                sandbox=config.sandbox,
                config=dict(config.config or {}),
                http=self._http,
            )
            return build_provider(provider, context)

        # Zero-config fallback: the mock provider works out of the box in sandbox.
        if provider == ProviderName.MOCK:
            context = ProviderContext(secret=_MOCK_SANDBOX_SECRET, sandbox=True, http=self._http)
            return build_provider(provider, context)

        raise NotFoundError(
            f"provider {provider.value!r} is not configured for this account",
            details={"provider": provider.value},
        )

    # -- Resilient execution ---------------------------------------------------
    def _breaker_for(self, provider: ProviderName) -> CircuitBreaker:
        breaker = self._breakers.get(provider)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self._settings.circuit_breaker_failure_threshold,
                reset_timeout=self._settings.circuit_breaker_reset_seconds,
                name=provider.value,
                # Card declines and validation problems must not trip the breaker.
                ignored_exceptions=(ProviderError,),
            )
            self._breakers[provider] = breaker
        return breaker

    async def execute(self, provider: ProviderName, operation: Callable[[], Awaitable[T]]) -> T:
        """Run a provider ``operation`` under retry + circuit breaker + metrics."""

        async def guarded() -> T:
            try:
                return await operation()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Normalise transport faults so retry/breaker treat them uniformly.
                raise ProviderUnavailableError(
                    "provider transport error", details={"provider": provider.value}
                ) from exc

        async def with_retry() -> T:
            return await retry_async(
                guarded,
                policy=RetryPolicy(max_attempts=self._settings.provider_max_retries),
                retry_on=(ProviderUnavailableError,),
            )

        breaker = self._breaker_for(provider)
        started = time.monotonic()
        outcome = "success"
        try:
            return await breaker.call(with_retry)
        except ProviderError:
            outcome = "declined"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            provider_calls_total.labels(provider=provider.value, outcome=outcome).inc()
            provider_call_duration_seconds.labels(provider=provider.value).observe(
                time.monotonic() - started
            )
