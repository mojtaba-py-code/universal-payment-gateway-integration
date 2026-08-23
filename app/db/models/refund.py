"""Refund model. Each row is one (possibly partial) refund against a payment."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domain.enums import RefundStatus


class Refund(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refunds"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus, native_enum=False, length=20),
        default=RefundStatus.PENDING,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    payment: Mapped["Payment"] = relationship(back_populates="refunds")


from app.db.models.payment import Payment  # noqa: E402
