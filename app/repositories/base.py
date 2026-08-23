"""Generic repository base.

Repositories encapsulate persistence so services depend on intent-revealing
methods (``get``, ``add``, ``list_for_owner``) rather than raw SQL. Each
repository is constructed with an :class:`AsyncSession`; the unit-of-work
boundary (commit/rollback) is owned by the caller via ``session_scope``.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)

    async def flush(self) -> None:
        await self.session.flush()
