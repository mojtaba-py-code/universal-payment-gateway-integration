"""Tests for the built-in mock/sandbox provider."""

from __future__ import annotations

import pytest
from app.core.money import Money
from app.domain.enums import CaptureMethod, PaymentStatus
from app.providers.base import ChargeRequest, ProviderContext
from app.providers.mock import MockProvider


def _provider() -> MockProvider:
    return MockProvider(ProviderContext(secret="whsec_test", sandbox=True))


async def test_create_automatic_captures() -> None:
    charge = await _provider().create_payment(
        ChargeRequest(amount=Money(1000, "USD"), capture_method=CaptureMethod.AUTOMATIC)
    )
    assert charge.status == PaymentStatus.CAPTURED
    assert charge.amount_captured == 1000
    assert charge.reference.startswith("mock_pay_")


async def test_create_manual_authorizes() -> None:
    charge = await _provider().create_payment(
        ChargeRequest(amount=Money(1000, "USD"), capture_method=CaptureMethod.MANUAL)
    )
    assert charge.status == PaymentStatus.AUTHORIZED
    assert charge.amount_captured == 0


async def test_forced_failure_paths() -> None:
    p = _provider()
    by_token = await p.create_payment(
        ChargeRequest(amount=Money(1000, "USD"), payment_method_token="pm_fail")
    )
    assert by_token.status == PaymentStatus.FAILED
    assert by_token.failure_reason == "card_declined"

    by_metadata = await p.create_payment(
        ChargeRequest(amount=Money(1000, "USD"), metadata={"force_failure": True})
    )
    assert by_metadata.status == PaymentStatus.FAILED


async def test_capture_cancel_refund() -> None:
    p = _provider()
    captured = await p.capture("mock_pay_1", Money(500, "USD"))
    assert captured.status == PaymentStatus.CAPTURED
    assert captured.amount_captured == 500

    canceled = await p.cancel("mock_pay_1")
    assert canceled.status == PaymentStatus.CANCELED

    refund = await p.refund("mock_pay_1", Money(250, "USD"), reason="requested")
    assert refund.status == "succeeded"
    assert refund.amount == 250


async def test_webhook_sign_and_verify_round_trip() -> None:
    p = _provider()
    body, headers = p.build_signed_webhook({"id": "evt_1", "type": "payment.captured"})
    event = p.verify_webhook(body, headers)
    assert event.event_id == "evt_1"
    assert event.event_type == "payment.captured"


async def test_webhook_bad_signature_rejected() -> None:
    from app.core.errors import SignatureInvalidError

    p = _provider()
    # Sign one body but present a different body under the same (recent) header.
    _, headers = p.build_signed_webhook({"id": "evt_1", "type": "x"})
    tampered_body = b'{"id":"evt_1","type":"x","injected":true}'
    with pytest.raises(SignatureInvalidError):
        p.verify_webhook(tampered_body, headers)
