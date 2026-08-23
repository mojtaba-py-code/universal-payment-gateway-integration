"""Targeted tests for cross-cutting units: errors, registry, session, limiter."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode, ProviderError
from app.db.base import Base
from app.db.session import create_engine, create_session_factory, session_scope
from app.domain.enums import ProviderName
from app.main import create_app
from app.providers import registry
from app.providers.base import ProviderContext


# -- errors ------------------------------------------------------------------
def test_domain_error_envelope_with_details_and_correlation() -> None:
    err = DomainError("boom", details={"x": 1}, code=ErrorCode.CONFLICT, http_status=409)
    env = err.to_envelope(correlation_id="cid-1")
    assert env["error"]["code"] == "conflict"
    assert env["error"]["details"] == {"x": 1}
    assert env["error"]["correlation_id"] == "cid-1"


def test_domain_error_envelope_minimal() -> None:
    env = ProviderError("declined").to_envelope()
    assert env["error"]["code"] == "provider_error"
    assert "details" not in env["error"]
    assert "correlation_id" not in env["error"]


# -- provider registry -------------------------------------------------------
def test_registry_lists_builtins() -> None:
    assert registry.is_registered(ProviderName.MOCK)
    assert ProviderName.STRIPE in registry.available_providers()


def test_registry_duplicate_registration_rejected() -> None:
    with pytest.raises(RuntimeError):

        @registry.register_provider(ProviderName.MOCK)
        class _Dupe:  # pragma: no cover - body never used
            pass


def test_build_provider_unknown_raises() -> None:
    # Temporarily drop a provider to simulate an unregistered name.
    saved = registry._REGISTRY.pop(ProviderName.STRIPE)
    try:
        with pytest.raises(ProviderError):
            registry.build_provider(ProviderName.STRIPE, ProviderContext(secret="x"))
    finally:
        registry._REGISTRY[ProviderName.STRIPE] = saved


# -- session scope -----------------------------------------------------------
async def test_session_scope_commit_and_rollback(settings: Settings) -> None:
    from app.db.models.user import User
    from app.security.passwords import hash_password

    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    async with session_scope(factory) as session:
        session.add(User(email="commit@x.co", hashed_password=hash_password("x" * 12)))

    # Rollback path: the exception propagates, and the row is not persisted.
    with pytest.raises(RuntimeError):
        async with session_scope(factory) as session:
            session.add(User(email="rollback@x.co", hashed_password=hash_password("x" * 12)))
            raise RuntimeError("force rollback")

    from app.repositories.users import UserRepository

    async with session_scope(factory) as session:
        users = UserRepository(session)
        assert await users.email_exists("commit@x.co")
        assert not await users.email_exists("rollback@x.co")

    await engine.dispose()


# -- rate limit middleware (integration) -------------------------------------
async def test_rate_limit_middleware_returns_429(tmp_path) -> None:
    settings = Settings(
        environment="testing",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'rl.db').as_posix()}",
        jwt_secret_key="unit-test-secret-key-at-least-32-characters",
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/")).status_code == 200
        blocked = await client.get("/")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in blocked.headers
