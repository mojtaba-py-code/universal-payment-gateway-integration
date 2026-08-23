"""API key generation and verification.

An API key is shown to the user exactly once at creation. We persist only a
SHA-256 hash of the full key (indexed for O(1) lookup) plus a short,
non-sensitive display prefix so users can recognise their keys in a dashboard.
Because the stored value is a hash, a database leak does not expose usable keys.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    #: The full secret. Returned to the caller once and never stored in cleartext.
    full_key: str
    #: SHA-256 hex digest of ``full_key``; safe to store and index.
    lookup_hash: str
    #: Human-friendly, non-secret prefix, e.g. ``"upgi_sk_a1b2c3d4…"``.
    display_prefix: str


def _hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def generate_api_key(prefix: str) -> GeneratedApiKey:
    """Create a new API key with the given human-readable ``prefix``."""
    secret = secrets.token_urlsafe(32)
    full_key = f"{prefix}_{secret}"
    return GeneratedApiKey(
        full_key=full_key,
        lookup_hash=_hash_key(full_key),
        display_prefix=f"{prefix}_{secret[:8]}…",
    )


def hash_for_lookup(full_key: str) -> str:
    """Return the indexed lookup hash for a presented key."""
    return _hash_key(full_key)


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of a presented key against a stored hash."""
    return hmac.compare_digest(_hash_key(full_key), stored_hash)
