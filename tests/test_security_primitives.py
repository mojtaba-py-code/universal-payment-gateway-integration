"""Tests for crypto, passwords, API keys, JWT, and signatures."""

from __future__ import annotations

import os
import time

import pytest
from app.core.config import Settings
from app.core.errors import AuthenticationError, ReplayDetectedError, SignatureInvalidError
from app.security import api_keys, signatures
from app.security.crypto import DecryptionError, SecretBox
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import TokenService


# -- crypto ------------------------------------------------------------------
def test_secret_box_round_trip() -> None:
    box = SecretBox.from_single_key(os.urandom(32))
    token = box.encrypt("sk_live_123", aad="tenant-1")
    assert box.decrypt(token, aad="tenant-1") == "sk_live_123"


def test_secret_box_rejects_wrong_aad() -> None:
    box = SecretBox.from_single_key(os.urandom(32))
    token = box.encrypt("secret", aad="tenant-1")
    with pytest.raises(DecryptionError):
        box.decrypt(token, aad="tenant-2")


def test_secret_box_rejects_tampering() -> None:
    box = SecretBox.from_single_key(os.urandom(32))
    token = box.encrypt("secret")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(DecryptionError):
        box.decrypt(tampered)


def test_secret_box_key_rotation() -> None:
    old_key, new_key = os.urandom(32), os.urandom(32)
    old_box = SecretBox.from_single_key(old_key, key_id="k1")
    token = old_box.encrypt("secret")
    # New box knows both keys but encrypts with k2; can still read old ciphertext.
    rotated = SecretBox(keys={"k1": old_key, "k2": new_key}, active_key_id="k2")
    assert rotated.decrypt(token) == "secret"


def test_secret_box_validates_key_length() -> None:
    with pytest.raises(ValueError):
        SecretBox.from_single_key(b"tooshort")


# -- passwords ---------------------------------------------------------------
def test_password_hash_and_verify() -> None:
    hashed = hash_password("hunter2-secure")
    assert hashed != "hunter2-secure"
    assert verify_password("hunter2-secure", hashed)
    assert not verify_password("wrong", hashed)


def test_password_empty_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_needs_rehash_on_garbage() -> None:
    assert needs_rehash("not-a-valid-hash") is True


# -- api keys ----------------------------------------------------------------
def test_api_key_generation_and_verification() -> None:
    generated = api_keys.generate_api_key("upgi_sk")
    assert generated.full_key.startswith("upgi_sk_")
    assert api_keys.verify_api_key(generated.full_key, generated.lookup_hash)
    assert not api_keys.verify_api_key("upgi_sk_wrong", generated.lookup_hash)
    assert "…" in generated.display_prefix


# -- JWT ---------------------------------------------------------------------
def _settings() -> Settings:
    return Settings(
        jwt_secret_key="x" * 40,
        access_token_ttl_seconds=1,
        environment="testing",
    )


def test_jwt_access_round_trip() -> None:
    service = TokenService(_settings())
    token = service.create_access_token("user-1", ("payments:read",))
    claims = service.decode(token, expected_type="access")
    assert claims.subject == "user-1"
    assert "payments:read" in claims.scopes


def test_jwt_wrong_type_rejected() -> None:
    service = TokenService(_settings())
    refresh = service.create_refresh_token("user-1")
    with pytest.raises(AuthenticationError):
        service.decode(refresh, expected_type="access")


def test_jwt_expired_rejected() -> None:
    from datetime import UTC, datetime, timedelta

    base = datetime(2020, 1, 1, tzinfo=UTC)
    service = TokenService(_settings(), now=lambda: base)
    token = service.create_access_token("user-1")
    # Decode "later" than expiry using a fresh service anchored in the future.
    future = TokenService(_settings(), now=lambda: base + timedelta(hours=1))
    with pytest.raises(AuthenticationError):
        future.decode(token, expected_type="access")


def test_jwt_tampered_signature_rejected() -> None:
    service = TokenService(_settings())
    token = service.create_access_token("user-1")
    with pytest.raises(AuthenticationError):
        service.decode(token + "x", expected_type="access")


# -- signatures --------------------------------------------------------------
def test_signature_round_trip() -> None:
    body = b'{"id":"evt_1"}'
    header = signatures.sign(body, "whsec", timestamp=1000)
    signatures.verify(body, header, "whsec", now=lambda: 1000)


def test_signature_replay_rejected() -> None:
    body = b"{}"
    header = signatures.sign(body, "whsec", timestamp=1000)
    with pytest.raises(ReplayDetectedError):
        signatures.verify(body, header, "whsec", tolerance_seconds=10, now=lambda: 5000)


def test_signature_wrong_secret_rejected() -> None:
    body = b"{}"
    header = signatures.sign(body, "whsec", timestamp=1000)
    with pytest.raises(SignatureInvalidError):
        signatures.verify(body, header, "other", now=lambda: 1000)


def test_signature_malformed_header_rejected() -> None:
    with pytest.raises(SignatureInvalidError):
        signatures.verify(b"{}", "garbage", "whsec", now=lambda: int(time.time()))
