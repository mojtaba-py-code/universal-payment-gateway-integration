"""Tests for meta, health, metrics, and global middleware behaviour."""

from __future__ import annotations

import httpx


async def test_root_metadata(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"]
    # Security headers applied globally.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    # Correlation id echoed back.
    assert resp.headers["X-Correlation-ID"]


async def test_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] == "up"


async def test_metrics_endpoint(client: httpx.AsyncClient) -> None:
    await client.get("/health/live")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "upgi_http_requests_total" in resp.text


async def test_incoming_correlation_id_is_propagated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/", headers={"X-Correlation-ID": "trace-123"})
    assert resp.headers["X-Correlation-ID"] == "trace-123"


async def test_unknown_route_returns_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
