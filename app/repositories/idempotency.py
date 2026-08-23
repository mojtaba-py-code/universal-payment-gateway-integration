"""Idempotency-key repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.idempotency import IdempotencyKey
from app.repositories.base import BaseRepository


class IdempotencyRepository(BaseRepository[IdempotencyKey]):
    model = IdempotencyKey

    async def get(  # type: ignore[override]
        self, owner_id: uuid.UUID, endpoint: str, key: str
    ) -> IdempotencyKey | None:
        result = await self.session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.owner_id == owner_id,
                IdempotencyKey.endpoint == endpoint,
                IdempotencyKey.key == key,
            )
        )
        return result.scalar_one_or_none()
