"""Payment repository, including owner-scoped listing with pagination/filter."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.db.models.payment import Payment
from app.domain.enums import PaymentStatus
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def get_for_owner(self, payment_id: uuid.UUID, owner_id: uuid.UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        status: PaymentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Payment], int]:
        conditions = [Payment.owner_id == owner_id]
        if status is not None:
            conditions.append(Payment.status == status)

        total_result = await self.session.execute(
            select(func.count()).select_from(Payment).where(*conditions)
        )
        total = int(total_result.scalar_one())

        result = await self.session.execute(
            select(Payment)
            .where(*conditions)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all(), total
