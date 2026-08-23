"""Resilience primitives: async retry with backoff, and a circuit breaker.

Downstream payment providers fail in bursts (network blips, brief outages,
rate limits). Two complementary patterns keep the platform stable:

* **Retry with exponential backoff + full jitter** smooths transient failures.
* **Circuit breaker** stops hammering a provider that is clearly down, failing
  fast (and cheaply) until a cool-off window elapses.

Both are provider-agnostic and unit-tested with a fake clock so tests never
actually sleep.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from app.core.errors import CircuitOpenError

T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Retry                                                                        #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class RetryPolicy:
    """Exponential backoff with full jitter."""

    max_attempts: int = 3
    base_delay: float = 0.2
    max_delay: float = 5.0
    multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        """Full-jitter delay for a 1-based attempt number."""
        ceiling = min(self.max_delay, self.base_delay * (self.multiplier ** (attempt - 1)))
        return random.uniform(0, ceiling)  # noqa: S311 - jitter, not security-sensitive


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retry_on: Iterable[type[BaseException]] = (Exception,),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Invoke ``func`` with retries. Re-raises the last error after exhaustion.

    ``sleep`` is injectable so tests can pass a no-op and stay instant.
    """
    policy = policy or RetryPolicy()
    retry_types = tuple(retry_on)
    last_exc: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await func()
        except retry_types as exc:
            last_exc = exc
            if attempt >= policy.max_attempts:
                break
            await sleep(policy.delay_for(attempt))
    assert last_exc is not None  # for type-checkers; loop always sets it
    raise last_exc


# --------------------------------------------------------------------------- #
# Circuit breaker                                                              #
# --------------------------------------------------------------------------- #
class CircuitState(StrEnum):
    CLOSED = "closed"  # healthy, calls pass through
    OPEN = "open"  # failing fast, calls rejected
    HALF_OPEN = "half_open"  # probing recovery with a single trial call


@dataclass(slots=True)
class CircuitBreaker:
    """A minimal, thread-safe-enough-for-asyncio circuit breaker.

    The breaker is keyed per provider by the caller. ``now`` is injectable to
    keep tests deterministic.
    """

    failure_threshold: int = 5
    reset_timeout: float = 30.0
    name: str = "default"
    #: Exceptions that pass through without counting as a failure *or* a success
    #: (e.g. a legitimate card decline — the provider itself is healthy).
    ignored_exceptions: tuple[type[BaseException], ...] = ()
    now: Callable[[], float] = field(default_factory=lambda: __import__("time").monotonic)

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self.now() - self._opened_at >= self.reset_timeout:
                    # Cool-off elapsed: allow a single probe.
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is open; provider temporarily unavailable",
                        details={"provider": self.name},
                    )

    async def _on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if self._state == CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self.now()

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Execute ``func`` under the breaker."""
        await self._before_call()
        try:
            result = await func()
        except self.ignored_exceptions:
            # Provider is healthy; the call failed for a business reason. Do not
            # change breaker state — just propagate.
            raise
        except Exception:
            await self._on_failure()
            raise
        else:
            await self._on_success()
            return result
