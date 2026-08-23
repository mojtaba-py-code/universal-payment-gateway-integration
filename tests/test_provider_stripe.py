"""Tests for the Stripe adapter using a mocked httpx transport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from app.core.errors import ProviderError
from app.core.money import Money
from app.domain.enums import CaptureMethod, PaymentStatus
from app.providers.base import ChargeRequest, ProviderContext
from app.providers.stripe import StripeProvider
from app.security import signatures


def _provider(handler) -> StripeProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.stripe.com")
    return StripeProvider(
        ProviderContext(secret="sk_test_123", http=client, config={"webhook_secret": "whsec"})
    )


async def test_create_payment_succeeded_maps_to_captured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/payment_intents"
        assert b"amount=1500" in request.content
        assert request.headers["Authorization"] == "Bearer sk_test_123"
        return httpx.Response(
            200, json={"id": "pi_1", "status": "succeeded", "amount_received": 1500}
        )

    charge = await _provider(handler).create_payment(
        ChargeRequest(amount=Money(1500, "USD"), payment_method_token="pm_card_visa")
    )
    assert charge.status == PaymentStatus.CAPTURED
    assert charge.reference == "pi_1"
    assert charge.amount_captured == 1500


async def test_create_manual_maps_to_authorized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert b"capture_method=manual" in request.content
        return httpx.Response(
            200, json={"id": "pi_2", "status": "requires_capture", "amount_received": 0}
        )

    charge = await _provider(handler).create_payment(
        ChargeRequest(amount=Money(2000, "USD"), capture_method=CaptureMethod.MANUAL)
    )
    assert charge.status == PaymentStatus.AUTHORIZED


async def test_capture_and_refund() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/capture"):
            return httpx.Response(
                200, json={"id": "pi_3", "status": "succeeded", "amount_received": 2000}
            )
        if request.url.path == "/v1/refunds":
            return httpx.Response(200, json={"id": "re_1", "status": "succeeded", "amount": 500})
        raise AssertionError("unexpected path")

    provider = _provider(handler)
    captured = await provider.capture("pi_3", Money(2000, "USD"))
    assert captured.status == PaymentStatus.CAPTURED

    refund = await provider.refund("pi_3", Money(500, "USD"), reason="dup")
    assert refund.reference == "re_1"
    assert refund.amount == 500


async def test_error_response_raises_provider_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={
                "error": {
                    "message": "Your card was declined.",
                    "code": "card_declined",
                    "type": "card_error",
                }
            },
        )

    with pytest.raises(ProviderError) as exc:
        await _provider(handler).create_payment(ChargeRequest(amount=Money(100, "USD")))
    assert "declined" in str(exc.value).lower()


async def test_cancel_maps_to_canceled() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "pi_4", "status": "canceled", "amount_received": 0})

    charge = await _provider(handler).cancel("pi_4")
    assert charge.status == PaymentStatus.CANCELED


def test_verify_webhook_uses_stripe_header() -> None:
    provider = _provider(lambda r: httpx.Response(200, json={}))
    payload = {"id": "evt_1", "type": "payment_intent.succeeded"}
    body = json.dumps(payload).encode()
    header = signatures.sign(body, "whsec")
    event = provider.verify_webhook(body, {"stripe-signature": header})
    assert event.event_id == "evt_1"
    assert event.event_type == "payment_intent.succeeded"
