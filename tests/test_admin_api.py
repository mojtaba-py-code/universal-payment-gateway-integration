"""End-to-end tests for admin/analytics endpoints and RBAC enforcement."""

from __future__ import annotations

import httpx

_ADMIN = "/api/v1/admin"
_PAYMENTS = "/api/v1/payments"


async def test_list_providers(client: httpx.AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.get(f"{_ADMIN}/providers", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "mock" in body["registered_providers"]
    assert "stripe" in body["registered_providers"]
    assert "USD" in body["supported_currencies"]


async def test_stats_reflect_payments(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    # Admin creates a couple of payments (admin has payments:write scope too).
    await client.post(
        _PAYMENTS, json={"amount_minor": 1000, "currency": "USD"}, headers=admin_headers
    )
    await client.post(
        _PAYMENTS, json={"amount_minor": 2000, "currency": "USD"}, headers=admin_headers
    )

    resp = await client.get(f"{_ADMIN}/stats", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_payments"] == 2
    assert body["by_status"]["captured"] == 2
    assert body["captured_minor_units"] == 3000


async def test_admin_requires_admin_scope(
    client: httpx.AsyncClient, merchant_headers: dict[str, str]
) -> None:
    resp = await client.get(f"{_ADMIN}/providers", headers=merchant_headers)
    assert resp.status_code == 403
