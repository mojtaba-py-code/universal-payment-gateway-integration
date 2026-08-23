"""Async engine and session management.

A single engine is created per process. The :func:`session_scope` async context
manager provides a transactional session that commits on success and rolls back
on any exception — the unit-of-work boundary for services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine appropriate for the configured database URL."""
    kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}
    # SQLite (used for tests / local) does not support connection pooling args.
    if not settings.database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )
    return create_async_engine(settings.database_url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional session boundary: commit on success, rollback on error."""
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
