"""Envelope encryption for provider credentials at rest (AES-256-GCM).

Provider API secrets (e.g. a Stripe secret key) must never be stored in
cleartext. :class:`SecretBox` encrypts them with AES-256-GCM — an authenticated
cipher, so tampering is detected on decrypt. A fresh random 96-bit nonce is used
per encryption and prepended to the ciphertext.

The master key is supplied by configuration (``UPGI_SECRET_ENCRYPTION_KEY``) and
supports **key rotation**: ciphertexts are tagged with a key id, and the box can
hold multiple keys so old data stays readable while new data uses the current
key.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_VERSION = b"\x01"


class DecryptionError(ValueError):
    """Raised when ciphertext is malformed or authentication fails."""


@dataclass(frozen=True, slots=True)
class SecretBox:
    """Authenticated encryption with support for key rotation.

    Args:
        keys: mapping of ``key_id -> 32-byte key``.
        active_key_id: id of the key used for new encryptions.
    """

    keys: dict[str, bytes]
    active_key_id: str

    def __post_init__(self) -> None:
        if self.active_key_id not in self.keys:
            raise ValueError("active_key_id must be present in keys")
        for kid, key in self.keys.items():
            if len(key) != 32:
                raise ValueError(f"key {kid!r} must be exactly 32 bytes for AES-256")

    @classmethod
    def from_single_key(cls, key: bytes, key_id: str = "primary") -> SecretBox:
        return cls(keys={key_id: key}, active_key_id=key_id)

    def encrypt(self, plaintext: str, *, aad: str | None = None) -> str:
        """Encrypt ``plaintext`` and return a base64 token embedding key id + nonce.

        ``aad`` (additional authenticated data) binds the ciphertext to a context
        (e.g. the owning tenant id) without encrypting it, preventing a
        ciphertext from being moved between records.
        """
        key = self.keys[self.active_key_id]
        nonce = os.urandom(_NONCE_BYTES)
        aead = AESGCM(key)
        ct = aead.encrypt(nonce, plaintext.encode("utf-8"), aad.encode() if aad else None)
        kid = self.active_key_id.encode("utf-8")
        # Framing: version | len(kid) | kid | nonce | ciphertext
        blob = _VERSION + bytes([len(kid)]) + kid + nonce + ct
        return base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt(self, token: str, *, aad: str | None = None) -> str:
        try:
            blob = base64.urlsafe_b64decode(token)
            if blob[:1] != _VERSION:
                raise DecryptionError("unsupported ciphertext version")
            kid_len = blob[1]
            offset = 2
            kid = blob[offset : offset + kid_len].decode("utf-8")
            offset += kid_len
            nonce = blob[offset : offset + _NONCE_BYTES]
            offset += _NONCE_BYTES
            ct = blob[offset:]
            key = self.keys.get(kid)
            if key is None:
                raise DecryptionError(f"unknown key id {kid!r}")
            aead = AESGCM(key)
            plaintext = aead.decrypt(nonce, ct, aad.encode() if aad else None)
            return plaintext.decode("utf-8")
        except (InvalidTag, IndexError, ValueError) as exc:
            raise DecryptionError("failed to decrypt secret") from exc
