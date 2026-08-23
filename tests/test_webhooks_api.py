"""End-to-end tests for the webhook endpoint (signature + idempotency)."""

from __future__ import annotations

import json

import httpx
from app.security import signatures
from app.services.gateway_manager import _MOCK_SANDBOX_SECRET

_WEBHOOK = "/api/v1/webhooks/mock"


def _signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    header = signatures.sign(body, _MOCK_SANDBOX_SECRET)
    return body, {"x-upgi-signature": header, "content-type": "application/json"}


async def test_valid_webhook_processed_then_deduplicated(client: httpx.AsyncClient) -> None:
    body, headers = _signed({"id": "evt_100", "type": "payment.captured"})

    first = await client.post(_WEBHOOK, content=body, headers=headers)
    assert first.status_code == 200
    assert first.json() == {
        "received": True,
        "duplicate": False,
        "event_id": "evt_100",
        "event_type": "payment.captured",
    }

    # Re-delivery of the same event is idempotent.
    second = await client.post(_WEBHOOK, content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


async def test_invalid_signature_rejected(client: httpx.AsyncClient) -> None:
    body, _ = _signed({"id": "evt_1", "type": "x"})
    resp = await client.post(
        _WEBHOOK, content=body, headers={"x-upgi-signature": "t=9999999999,v1=bad"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] in {"signature_invalid", "replay_detected"}
