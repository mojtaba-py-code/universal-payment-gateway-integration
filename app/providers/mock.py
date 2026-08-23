"""Mock / sandbox provider.

A fully functional, deterministic, offline provider used for local development,
automated tests, and the built-in payment simulator. It mimics the behaviour of
a real gateway (authorize → capture → refund/void) without any network calls,
and supports "magic" inputs to force specific outcomes:

* ``payment_method_token == "pm_fail"`` → the charge fails.
* ``metadata["force_failure"] is True`` → the charge fails.

Webhooks are signed with the same HMAC scheme (:mod:`app.security.signatures`)
used elsewhere, so the mock doubles as a webhook simulator.
"""

from __future__ import annotations

import json
import uuid

from app.core.money import Money
from app.domain.enums import CaptureMethod, PaymentStatus, ProviderName
from app.providers.base import (
    BasePaymentProvider,
    ChargeRequest,
    ProviderCharge,
    ProviderRefund,
    ProviderWebhook,
)
from app.providers.registry import register_provider
from app.security import signatures

_SIGNATURE_HEADER = "x-upgi-signature"


def _new_reference(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


@register_provider(ProviderName.MOCK)
class MockProvider(BasePaymentProvider):
    """Deterministic in-memory provider adapter."""

    def _should_fail(self, request: ChargeRequest) -> bool:
        return (
            request.payment_method_token == "pm_fail"  # noqa: S105 - sentinel token, not a secret
            or bool(request.metadata.get("force_failure"))
        )

    async def create_payment(self, request: ChargeRequest) -> ProviderCharge:
        reference = _new_reference("mock_pay")
        if self._should_fail(request):
            return ProviderCharge(
                reference=reference,
                status=PaymentStatus.FAILED,
                amount_captured=0,
                failure_reason="card_declined",
                raw={"simulated": True},
            )
        if request.capture_method == CaptureMethod.MANUAL:
            return ProviderCharge(
                reference=reference,
                status=PaymentStatus.AUTHORIZED,
                amount_captured=0,
                raw={"simulated": True, "captured": False},
            )
        return ProviderCharge(
            reference=reference,
            status=PaymentStatus.CAPTURED,
            amount_captured=request.amount.minor_units,
            raw={"simulated": True, "captured": True},
        )

    async def capture(self, reference: str, amount: Money) -> ProviderCharge:
        return ProviderCharge(
            reference=reference,
            status=PaymentStatus.CAPTURED,
            amount_captured=amount.minor_units,
            raw={"simulated": True},
        )

    async def cancel(self, reference: str) -> ProviderCharge:
        return ProviderCharge(
            reference=reference,
            status=PaymentStatus.CANCELED,
            amount_captured=0,
            raw={"simulated": True},
        )

    async def refund(
        self, reference: str, amount: Money, reason: str | None = None
    ) -> ProviderRefund:
        return ProviderRefund(
            reference=_new_reference("mock_ref"),
            status="succeeded",
            amount=amount.minor_units,
            raw={"simulated": True, "payment": reference, "reason": reason},
        )

    # -- Webhook simulator -----------------------------------------------------
    def build_signed_webhook(
        self, payload: dict, *, timestamp: int | None = None
    ) -> tuple[bytes, dict[str, str]]:
        """Helper (used by the simulator/tests) to produce a signed webhook."""
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        header = signatures.sign(body, self.context.secret, timestamp=timestamp)
        return body, {_SIGNATURE_HEADER: header}

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhook:
        header = headers.get(_SIGNATURE_HEADER, "")
        signatures.verify(body, header, self.context.secret)
        payload = json.loads(body.decode("utf-8"))
        return ProviderWebhook(
            event_id=str(payload["id"]),
            event_type=str(payload["type"]),
            payload=payload,
        )
