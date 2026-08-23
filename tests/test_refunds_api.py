"""End-to-end tests for the refund endpoints."""

from __future__ import annotations

import httpx

_PAYMENTS = "/api/v1/payments"


async def _capture_payment(client: httpx.AsyncClient, headers: dict[str, str], amount: int) -> str:
    created = await client.post(
        _PAYMENTS, json={"amount_minor": amount, "currency": "USD"}, headers=headers
    )
    assert created.json()["status"] == "captured"
    return created.json()["id"]


async def test_full_refund(client: httpx.AsyncClient, merchant_headers: dict[str, str]) -> None:
    payment_id = await _capture_payment(client, merchant_headers, 4000)
    resp = await client.post(f"{_PAYMENTS}/{payment_id}/refunds", json={}, headers=merchant_headers)
    assert resp.status_code == 201
    assert resp.json()["amount"]["minor_units"] == 4000

    payment = await client.get(f"{_PAYMENTS}/{payment_id}", headers=merchant_headers)
    assert payment.json()["status"] == "refunded"
    assert payment.json()["amount_refunded"]["minor_units"] == 4000


async def test_partial_then_full_refund(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    payment_id = await _capture_payment(client, merchant_headers, 4000)

    first = await client.post(
        f"{_PAYMENTS}/{payment_id}/refunds", json={"amount_minor": 1500}, headers=merchant_headers
    )
    assert first.status_code == 201
    payment = await client.get(f"{_PAYMENTS}/{payment_id}", headers=merchant_headers)
    assert payment.json()["status"] == "partially_refunded"

    second = await client.post(
        f"{_PAYMENTS}/{payment_id}/refunds", json={"amount_minor": 2500}, headers=merchant_headers
    )
    assert second.status_code == 201
    payment = await client.get(f"{_PAYMENTS}/{payment_id}", headers=merchant_headers)
    assert payment.json()["status"] == "refunded"


async def test_over_refund_rejected(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    payment_id = await _capture_payment(client, merchant_headers, 1000)
    resp = await client.post(
        f"{_PAYMENTS}/{payment_id}/refunds", json={"amount_minor": 5000}, headers=merchant_headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_refund_uncaptured_rejected(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    created = await client.post(
        _PAYMENTS,
        json={"amount_minor": 1000, "currency": "USD", "capture_method": "manual"},
        headers=merchant_headers,
    )
    payment_id = created.json()["id"]
    resp = await client.post(f"{_PAYMENTS}/{payment_id}/refunds", json={}, headers=merchant_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invalid_state"


async def test_refund_idempotency(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    payment_id = await _capture_payment(client, merchant_headers, 2000)
    headers = {**merchant_headers, "Idempotency-Key": "refund-1"}
    first = await client.post(
        f"{_PAYMENTS}/{payment_id}/refunds", json={"amount_minor": 500}, headers=headers
    )
    second = await client.post(
        f"{_PAYMENTS}/{payment_id}/refunds", json={"amount_minor": 500}, headers=headers
    )
    assert first.json()["id"] == second.json()["id"]

    payment = await client.get(f"{_PAYMENTS}/{payment_id}", headers=merchant_headers)
    # Only one refund applied despite the retry.
    assert payment.json()["amount_refunded"]["minor_units"] == 500
