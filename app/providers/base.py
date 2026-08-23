"""Provider-agnostic interface (the Adapter/Strategy seam).

Every payment provider is wrapped in an adapter that implements
:class:`BasePaymentProvider`, translating our unified request/result DTOs to and
from the provider's native API. The rest of the system depends only on this
interface — adding a new provider never changes business logic (Open/Closed
Principle).

DTOs are plain, immutable dataclasses so the domain has no coupling to any HTTP
client or provider SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.money import Money
from app.domain.enums import CaptureMethod, PaymentMethodType, PaymentStatus, ProviderName


# --------------------------------------------------------------------------- #
# Request / result DTOs                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ChargeRequest:
    """A request to create a payment at a provider."""

    amount: Money
    capture_method: CaptureMethod = CaptureMethod.AUTOMATIC
    method_type: PaymentMethodType = PaymentMethodType.CARD
    #: An opaque, provider-specific payment method token (never raw PAN).
    payment_method_token: str | None = None
    description: str | None = None
    customer_reference: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderCharge:
    """Normalised result of a create/authorize/capture operation."""

    reference: str
    status: PaymentStatus
    amount_captured: int
    raw: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRefund:
    reference: str
    status: str
    amount: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderWebhook:
    """A verified, normalised inbound webhook event."""

    event_id: str
    event_type: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderContext:
    """Everything an adapter needs to talk to its backend for one operation.

    The ``secret`` is already decrypted by the caller; adapters must not log it.
    ``http`` is an injected async client so tests can supply a mock transport.
    """

    secret: str
    sandbox: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    http: Any | None = None  # httpx.AsyncClient in production; kept loose for testing


# --------------------------------------------------------------------------- #
# Adapter interface                                                            #
# --------------------------------------------------------------------------- #
class BasePaymentProvider(ABC):
    """Unified interface every provider adapter implements."""

    name: ProviderName

    def __init__(self, context: ProviderContext) -> None:
        self.context = context

    @abstractmethod
    async def create_payment(self, request: ChargeRequest) -> ProviderCharge:
        """Create a payment. Honors ``request.capture_method``."""

    @abstractmethod
    async def capture(self, reference: str, amount: Money) -> ProviderCharge:
        """Capture (part of) a previously authorized payment."""

    @abstractmethod
    async def cancel(self, reference: str) -> ProviderCharge:
        """Cancel/void an authorized (uncaptured) payment."""

    @abstractmethod
    async def refund(
        self, reference: str, amount: Money, reason: str | None = None
    ) -> ProviderRefund:
        """Refund (part of) a captured payment."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhook:
        """Verify a webhook signature and return the normalised event."""
