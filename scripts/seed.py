"""Seed script: create an initial admin user and a demo merchant.

Idempotent — running it repeatedly will not create duplicates. Intended for
local/staging bootstrap only. Passwords are read from the environment so no
secret is written to source.

Usage:
    python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine, create_session_factory, session_scope
from app.domain.enums import UserRole
from app.repositories.users import UserRepository
from app.security.passwords import hash_password


async def _seed() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)

    admin_email = os.environ.get("UPGI_SEED_ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("UPGI_SEED_ADMIN_PASSWORD", "change-me-admin-123")

    async with session_scope(factory) as session:
        users = UserRepository(session)
        from app.db.models.user import User

        if not await users.email_exists(admin_email):
            users.add(
                User(
                    email=admin_email,
                    hashed_password=hash_password(admin_password),
                    full_name="Administrator",
                    role=UserRole.ADMIN,
                )
            )
            print(f"created admin: {admin_email}")
        else:
            print(f"admin already exists: {admin_email}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_seed())
