"""JWT access/refresh token issuance and verification.

Tokens are signed with HMAC (HS256 by default). Every token carries standard
registered claims (``iss``, ``aud``, ``exp``, ``iat``, ``nbf``, ``jti``) plus a
``type`` claim distinguishing access from refresh tokens, so a refresh token can
never be replayed as an access token.

Time is injected via a ``now`` callable so token expiry can be tested
deterministically.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.config import Settings
from app.core.errors import AuthenticationError

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    token_type: TokenType
    jti: str
    expires_at: datetime
    scopes: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


class TokenService:
    """Issues and verifies JWTs bound to a :class:`Settings` instance."""

    def __init__(self, settings: Settings, *, now: Callable[[], datetime] | None = None) -> None:
        self._settings = settings
        self._now = now or (lambda: datetime.now(UTC))

    # -- Issuance --------------------------------------------------------------
    def _issue(
        self, subject: str, token_type: TokenType, ttl_seconds: int, scopes: tuple[str, ...]
    ) -> str:
        issued_at = self._now()
        payload: dict[str, Any] = {
            "sub": subject,
            "type": token_type,
            "scopes": list(scopes),
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(seconds=ttl_seconds)).timestamp()),
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(
            payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm
        )

    def create_access_token(self, subject: str, scopes: tuple[str, ...] = ()) -> str:
        return self._issue(subject, "access", self._settings.access_token_ttl_seconds, scopes)

    def create_refresh_token(self, subject: str) -> str:
        return self._issue(subject, "refresh", self._settings.refresh_token_ttl_seconds, ())

    # -- Verification ----------------------------------------------------------
    def decode(self, token: str, *, expected_type: TokenType) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret_key,
                algorithms=[self._settings.jwt_algorithm],
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={"require": ["exp", "iat", "sub", "jti"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError("Invalid authentication token") from exc

        if payload.get("type") != expected_type:
            raise AuthenticationError(
                f"Expected a {expected_type} token but received {payload.get('type')!r}"
            )

        return TokenClaims(
            subject=str(payload["sub"]),
            token_type=expected_type,
            jti=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            scopes=tuple(payload.get("scopes", ())),
            raw=payload,
        )
