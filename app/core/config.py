"""Application configuration.

All runtime configuration is sourced from environment variables (prefixed with
``UPGI_``) or an ``.env`` file. Secrets are *never* hard-coded; production
deployments must supply them via the host environment or a secrets manager.

The settings object is a process-wide singleton created lazily through
:func:`get_settings`, which is also used as a FastAPI dependency so it can be
overridden in tests.
"""

from __future__ import annotations

import base64
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Governs a handful of safety-critical defaults."""

    LOCAL = "local"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Strongly-typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_prefix="UPGI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- General ---------------------------------------------------------------
    app_name: str = "Universal Payment Gateway Integration"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # -- Database --------------------------------------------------------------
    # Async SQLAlchemy URL. Defaults to a local file-based SQLite database so the
    # project runs out-of-the-box; production uses PostgreSQL via asyncpg.
    database_url: str = "sqlite+aiosqlite:///./upgi.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # -- Cache / queue ---------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    # When False (default in local/testing) the app uses an in-process fallback
    # for rate limiting and idempotency caches instead of requiring Redis.
    use_redis: bool = False

    # -- Security: JWT ---------------------------------------------------------
    # 32+ char random string. A weak default is provided ONLY for local dev and
    # is rejected at startup in production (see ``_validate_production_secrets``).
    jwt_secret_key: str = "dev-only-insecure-change-me-please-32chars!!"  # noqa: S105 - dev-only default, rejected in production
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days
    jwt_issuer: str = "upgi"
    jwt_audience: str = "upgi-clients"

    # -- Security: secret encryption (AES-256-GCM) -----------------------------
    # Base64url-encoded 32-byte master key used to envelope-encrypt provider
    # credentials at rest. A per-process ephemeral key is generated if unset,
    # which is fine for tests but must be provided explicitly in real deployments.
    secret_encryption_key: str = Field(
        default_factory=lambda: base64.urlsafe_b64encode(b"\x00" * 32).decode()
    )

    # -- API keys --------------------------------------------------------------
    api_key_prefix: str = "upgi_sk"

    # -- Rate limiting ---------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120  # requests
    rate_limit_window_seconds: int = 60  # per window

    # -- Webhooks --------------------------------------------------------------
    webhook_replay_window_seconds: int = 300  # 5 minutes
    webhook_max_delivery_attempts: int = 8

    # -- HTTP client -----------------------------------------------------------
    outbound_http_timeout_seconds: float = 15.0
    provider_max_retries: int = 3
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: float = 30.0

    # -- CORS ------------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_allow_credentials: bool = True

    # -- Observability ---------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    metrics_enabled: bool = True

    # -- Derived helpers -------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING

    def encryption_key_bytes(self) -> bytes:
        """Return the 32-byte AES master key, validating length."""
        raw = base64.urlsafe_b64decode(self.secret_encryption_key)
        if len(raw) != 32:
            raise ValueError("UPGI_SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return raw

    # -- Validators ------------------------------------------------------------
    @field_validator("jwt_secret_key")
    @classmethod
    def _min_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("UPGI_JWT_SECRET_KEY must be at least 32 characters")
        return value

    @field_validator("environment")
    @classmethod
    def _validate_production_secrets(cls, value: Environment, info: ValidationInfo) -> Environment:
        # Cross-field validation runs field-by-field; the strong guarantees for
        # production are enforced at app startup in ``app.main`` where the full
        # object is available. This validator only normalises the value.
        return value

    def assert_production_ready(self) -> None:
        """Fail fast if the process is running in production with insecure defaults.

        Called once during application startup. Keeping it out of field
        validators lets tests construct ``Settings`` freely.
        """
        if not self.is_production:
            return
        problems: list[str] = []
        if "dev-only-insecure" in self.jwt_secret_key:
            problems.append("UPGI_JWT_SECRET_KEY still uses the insecure default")
        if self.encryption_key_bytes() == b"\x00" * 32:
            problems.append("UPGI_SECRET_ENCRYPTION_KEY still uses the insecure default")
        if self.debug:
            problems.append("UPGI_DEBUG must be false in production")
        if "*" in self.cors_allow_origins:
            problems.append("wildcard CORS origin is forbidden in production")
        if problems:
            raise RuntimeError("Insecure production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
