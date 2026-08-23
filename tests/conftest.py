"""Shared pytest fixtures.

Each test gets an isolated FastAPI application backed by a throwaway SQLite
database file, so tests are hermetic and can run in parallel. Helper fixtures
mint authenticated request headers for the three RBAC roles.
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
import pytest_asyncio
from app.core.config import Settings
from app.db.base import Base
from app.domain.enums import UserRole
from app.domain.rbac import scopes_for_role
from app.main import create_app
from app.security.passwords import hash_password


@pytest.fixture
def settings(tmp_path) -> Settings:
    db_path = tmp_path / "test.db"
    return Settings(
        environment="testing",
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        secret_encryption_key=base64.urlsafe_b64encode(os.urandom(32)).decode(),
        jwt_secret_key="unit-test-secret-key-at-least-32-characters",
        rate_limit_enabled=False,
        log_json=False,
        metrics_enabled=True,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest_asyncio.fixture(autouse=True)
async def _create_schema(app) -> AsyncIterator[None]:
    engine = app.state.engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def make_auth_headers(app) -> Callable[..., Awaitable[dict[str, str]]]:
    """Return an async factory that creates a user of a given role and returns
    Bearer auth headers for it."""

    async def _factory(role: UserRole = UserRole.MERCHANT) -> dict[str, str]:
        from app.db.models.user import User

        factory = app.state.session_factory
        async with factory() as session:
            user = User(
                email=f"{role.value}-{uuid.uuid4().hex[:8]}@example.com",
                hashed_password=hash_password("correct horse battery"),
                role=role,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            user_id, user_role = user.id, user.role

        token = app.state.token_service.create_access_token(
            str(user_id), scopes_for_role(user_role)
        )
        return {"Authorization": f"Bearer {token}"}

    return _factory


@pytest_asyncio.fixture
async def merchant_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(UserRole.MERCHANT)


@pytest_asyncio.fixture
async def admin_headers(make_auth_headers) -> dict[str, str]:
    return await make_auth_headers(UserRole.ADMIN)
