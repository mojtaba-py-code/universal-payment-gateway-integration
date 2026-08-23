"""Stripe adapter.

Implements the unified :class:`BasePaymentProvider` interface against Stripe's
PaymentIntents + Refunds REST API using ``httpx``. The adapter is transport-
injectable: in tests we pass an ``httpx.AsyncClient`` backed by a
``MockTransport``, so the full request-building and response-mapping logic is
exercised without any network access.

Stripe's webhook signature scheme (``Stripe-Signature: t=…,v1=…``, HMAC-SHA256
over ``"{t}.{body}"``) matches :mod:`app.security.signatures`, which we reuse.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import ProviderError
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

_LIVE_BASE_URL = "https://api.stripe.com"
_STRIPE_SIGNATURE_HEADER = "stripe-signature"

# Stripe PaymentIntent status -> our unified status.
_STATUS_MAP = {
    "succeeded": PaymentStatus.CAPTURED,
    "requires_capture": PaymentStatus.AUTHORIZED,
    "canceled": PaymentStatus.CANCELED,
    "processing": PaymentStatus.REQUIRES_CONFIRMATION,
    "requires_confirmation": PaymentStatus.REQUIRES_CONFIRMATION,
    "requires_action": PaymentStatus.REQUIRES_CONFIRMATION,
    "requires_payment_method": PaymentStatus.FAILED,
}


@register_provider(ProviderName.STRIPE)
class StripeProvider(BasePaymentProvider):
    """Stripe PaymentIntents adapter."""

    def _client(self) -> httpx.AsyncClient:
        if self.context.http is not None:
            return self.context.http
        base_url = self.context.config.get("base_url", _LIVE_BASE_URL)
        return httpx.AsyncClient(base_url=base_url, timeout=15.0)

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.context.secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _post(
        self, path: str, data: dict[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        client = self._client()
        response = await client.post(path, data=data, headers=self._headers(idempotency_key))
        payload: dict[str, Any] = response.json()
        if response.status_code >= 400:
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise ProviderError(
                err.get("message", "Stripe request failed"),
                details={"provider": "stripe", "type": err.get("type"), "code": err.get("code")},
            )
        return payload

    def _to_charge(self, intent: dict[str, Any]) -> ProviderCharge:
        status = _STATUS_MAP.get(intent.get("status", ""), PaymentStatus.FAILED)
        amount_captured = int(intent.get("amount_received", 0) or 0)
        failure = None
        if status == PaymentStatus.FAILED:
            last_err = intent.get("last_payment_error") or {}
            failure = last_err.get("message", "payment_failed")
        return ProviderCharge(
            reference=str(intent["id"]),
            status=status,
            amount_captured=amount_captured,
            raw=intent,
            failure_reason=failure,
        )

    # -- Interface -------------------------------------------------------------
    async def create_payment(self, request: ChargeRequest) -> ProviderCharge:
        data: dict[str, Any] = {
            "amount": request.amount.minor_units,
            "currency": request.amount.currency.lower(),
            "capture_method": "manual"
            if request.capture_method == CaptureMethod.MANUAL
            else "automatic",
            "confirm": "true",
        }
        if request.payment_method_token:
            data["payment_method"] = request.payment_method_token
        if request.description:
            data["description"] = request.description
        for key, value in request.metadata.items():
            data[f"metadata[{key}]"] = value
        intent = await self._post(
            "/v1/payment_intents", data, idempotency_key=request.idempotency_key
        )
        return self._to_charge(intent)

    async def capture(self, reference: str, amount: Money) -> ProviderCharge:
        intent = await self._post(
            f"/v1/payment_intents/{reference}/capture",
            {"amount_to_capture": amount.minor_units},
        )
        return self._to_charge(intent)

    async def cancel(self, reference: str) -> ProviderCharge:
        intent = await self._post(f"/v1/payment_intents/{reference}/cancel", {})
        return self._to_charge(intent)

    async def refund(
        self, reference: str, amount: Money, reason: str | None = None
    ) -> ProviderRefund:
        data: dict[str, Any] = {"payment_intent": reference, "amount": amount.minor_units}
        if reason:
            data["metadata[reason]"] = reason
        refund = await self._post("/v1/refunds", data)
        return ProviderRefund(
            reference=str(refund["id"]),
            status=str(refund.get("status", "pending")),
            amount=int(refund.get("amount", amount.minor_units)),
            raw=refund,
        )

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhook:
        secret = self.context.config.get("webhook_secret") or self.context.secret
        header = headers.get(_STRIPE_SIGNATURE_HEADER, "")
        signatures.verify(body, header, secret)
        import json

        payload = json.loads(body.decode("utf-8"))
        return ProviderWebhook(
            event_id=str(payload["id"]),
            event_type=str(payload["type"]),
            payload=payload,
        )
