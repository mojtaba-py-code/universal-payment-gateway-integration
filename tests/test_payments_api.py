"""End-to-end tests for the payment endpoints."""

from __future__ import annotations

import httpx
import pytest
from app.domain.enums import UserRole

_PAYMENTS = "/api/v1/payments"


async def test_create_automatic_payment_is_captured(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    resp = await client.post(
        _PAYMENTS,
        json={
            "provider": "mock",
            "amount_minor": 5000,
            "currency": "USD",
            "description": "Order 1",
        },
        headers=merchant_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "captured"
    assert body["amount"]["minor_units"] == 5000
    assert body["amount"]["display"] == "50.00 USD"
    assert body["amount_captured"]["minor_units"] == 5000


async def test_manual_capture_flow(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    created = await client.post(
        _PAYMENTS,
        json={"amount_minor": 3000, "currency": "USD", "capture_method": "manual"},
        headers=merchant_headers,
    )
    assert created.json()["status"] == "authorized"
    payment_id = created.json()["id"]

    captured = await client.post(
        f"{_PAYMENTS}/{payment_id}/capture", json={}, headers=merchant_headers
    )
    assert captured.status_code == 200
    assert captured.json()["status"] == "captured"


async def test_cancel_flow(client: httpx.AsyncClient, merchant_headers: dict[str, str]) -> None:
    created = await client.post(
        _PAYMENTS,
        json={"amount_minor": 3000, "currency": "USD", "capture_method": "manual"},
        headers=merchant_headers,
    )
    payment_id = created.json()["id"]
    canceled = await client.post(f"{_PAYMENTS}/{payment_id}/cancel", headers=merchant_headers)
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


async def test_failed_payment(client: httpx.AsyncClient, merchant_headers: dict[str, str]) -> None:
    resp = await client.post(
        _PAYMENTS,
        json={"amount_minor": 1000, "currency": "USD", "payment_method_token": "pm_fail"},
        headers=merchant_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "failed"
    assert resp.json()["failure_reason"] == "card_declined"


async def test_get_and_list_payments(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    created = await client.post(
        _PAYMENTS, json={"amount_minor": 1000, "currency": "USD"}, headers=merchant_headers
    )
    payment_id = created.json()["id"]

    got = await client.get(f"{_PAYMENTS}/{payment_id}", headers=merchant_headers)
    assert got.status_code == 200

    listed = await client.get(_PAYMENTS, headers=merchant_headers)
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1

    filtered = await client.get(f"{_PAYMENTS}?status=captured", headers=merchant_headers)
    assert filtered.json()["meta"]["total"] == 1
    empty = await client.get(f"{_PAYMENTS}?status=refunded", headers=merchant_headers)
    assert empty.json()["meta"]["total"] == 0


async def test_idempotent_create(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    headers = {**merchant_headers, "Idempotency-Key": "abc-123"}
    payload = {"amount_minor": 2500, "currency": "USD"}

    first = await client.post(_PAYMENTS, json=payload, headers=headers)
    second = await client.post(_PAYMENTS, json=payload, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    # Only one payment actually persisted.
    listed = await client.get(_PAYMENTS, headers=merchant_headers)
    assert listed.json()["meta"]["total"] == 1


async def test_idempotency_conflict_on_different_body(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    headers = {**merchant_headers, "Idempotency-Key": "same-key"}
    await client.post(_PAYMENTS, json={"amount_minor": 100, "currency": "USD"}, headers=headers)
    conflict = await client.post(
        _PAYMENTS, json={"amount_minor": 999, "currency": "USD"}, headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


async def test_create_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post(_PAYMENTS, json={"amount_minor": 100, "currency": "USD"})
    assert resp.status_code == 401


async def test_viewer_cannot_create(client: httpx.AsyncClient, make_auth_headers) -> None:
    viewer = await make_auth_headers(UserRole.VIEWER)
    resp = await client.post(
        _PAYMENTS, json={"amount_minor": 100, "currency": "USD"}, headers=viewer
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(
    "payload",
    [
        {"amount_minor": 0, "currency": "USD"},
        {"amount_minor": 100, "currency": "XXX"},
        {"amount_minor": -5, "currency": "USD"},
    ],
)
async def test_validation_errors(
    client: httpx.AsyncClient, merchant_headers: dict[str, str], payload: dict
) -> None:
    resp = await client.post(_PAYMENTS, json=payload, headers=merchant_headers)
    assert resp.status_code == 422


async def test_other_owner_cannot_see_payment(
    client: httpx.AsyncClient, merchant_headers: dict[str, str], make_auth_headers
) -> None:
    created = await client.post(
        _PAYMENTS, json={"amount_minor": 100, "currency": "USD"}, headers=merchant_headers
    )
    payment_id = created.json()["id"]
    other = await make_auth_headers(UserRole.MERCHANT)
    resp = await client.get(f"{_PAYMENTS}/{payment_id}", headers=other)
    assert resp.status_code == 404
