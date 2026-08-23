"""Refund repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.db.models.refund import Refund
from app.repositories.base import BaseRepository


class RefundRepository(BaseRepository[Refund]):
    model = Refund

    async def list_for_payment(self, payment_id: uuid.UUID) -> Sequence[Refund]:
        result = await self.session.execute(
            select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.created_at)
        )
        return result.scalars().all()
