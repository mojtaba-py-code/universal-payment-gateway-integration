"""HMAC webhook signatures with replay protection.

Outbound webhooks we emit — and inbound webhooks from providers that use this
scheme — are signed with HMAC-SHA256 over ``"{timestamp}.{body}"``. The signed
timestamp lets the receiver reject stale deliveries (replay protection) within a
configurable tolerance window.

Header format (Stripe-compatible): ``t=<unix_ts>,v1=<hex_digest>``.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable

from app.core.errors import ReplayDetectedError, SignatureInvalidError


def _compute(secret: str, timestamp: int, body: bytes) -> str:
    signed_payload = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def sign(body: bytes, secret: str, *, timestamp: int | None = None) -> str:
    """Return a signature header for ``body``."""
    ts = timestamp if timestamp is not None else int(time.time())
    digest = _compute(secret, ts, body)
    return f"t={ts},v1={digest}"


def _parse_header(header: str) -> tuple[int, list[str]]:
    ts: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                ts = int(value)
            except ValueError as exc:
                raise SignatureInvalidError("malformed timestamp in signature header") from exc
        elif key == "v1":
            signatures.append(value)
    if ts is None or not signatures:
        raise SignatureInvalidError("signature header missing timestamp or v1 signature")
    return ts, signatures


def verify(
    body: bytes,
    header: str,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Callable[[], int] = lambda: int(time.time()),
) -> None:
    """Validate a signature header. Raises on any failure.

    Raises:
        SignatureInvalidError: signature does not match (or header malformed).
        ReplayDetectedError: the signed timestamp is outside the tolerance window.
    """
    ts, signatures = _parse_header(header)

    if abs(now() - ts) > tolerance_seconds:
        raise ReplayDetectedError(
            "webhook timestamp outside tolerance window",
            details={"tolerance_seconds": tolerance_seconds},
        )

    expected = _compute(secret, ts, body)
    # Constant-time comparison against every provided v1 signature.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise SignatureInvalidError("webhook signature verification failed")
