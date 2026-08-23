"""API key repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.db.models.api_key import ApiKey
from app.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    model = ApiKey

    async def get_by_hash(self, hashed_key: str) -> ApiKey | None:
        result = await self.session.execute(select(ApiKey).where(ApiKey.hashed_key == hashed_key))
        return result.scalar_one_or_none()

    async def list_for_owner(self, owner_id: uuid.UUID) -> Sequence[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id == owner_id).order_by(ApiKey.created_at.desc())
        )
        return result.scalars().all()
