"""Admin & analytics endpoints (require the admin scope)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import SessionDep, require_scope
from app.core.money import CURRENCY_EXPONENTS
from app.db.models.payment import Payment
from app.db.models.user import User
from app.domain.rbac import SCOPE_ADMIN
from app.providers.registry import available_providers

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_scope(SCOPE_ADMIN))]


class ProvidersInfo(BaseModel):
    registered_providers: list[str]
    supported_currencies: list[str]


class PaymentStats(BaseModel):
    total_payments: int
    by_status: dict[str, int]
    captured_minor_units: int


@router.get("/providers", response_model=ProvidersInfo, summary="List registered providers")
async def list_providers(_: AdminUser) -> ProvidersInfo:
    return ProvidersInfo(
        registered_providers=[p.value for p in available_providers()],
        supported_currencies=sorted(CURRENCY_EXPONENTS.keys()),
    )


@router.get("/stats", response_model=PaymentStats, summary="Aggregate payment statistics")
async def payment_stats(user: AdminUser, session: SessionDep) -> PaymentStats:
    status_rows = await session.execute(
        select(Payment.status, func.count()).group_by(Payment.status)
    )
    by_status = {status.value: count for status, count in status_rows.all()}

    total = sum(by_status.values())
    captured_row = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_captured), 0))
    )
    captured = int(captured_row.scalar_one())

    return PaymentStats(total_payments=total, by_status=by_status, captured_minor_units=captured)
