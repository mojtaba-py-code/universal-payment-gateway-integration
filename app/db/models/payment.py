"""Payment (a.k.a. payment intent) model.

Amounts are stored as integer minor units plus an ISO-4217 currency, mirroring
the :class:`app.core.money.Money` value object. ``amount_captured`` and
``amount_refunded`` track partial operations so the refund engine can enforce
that refunds never exceed captured funds.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domain.enums import CaptureMethod, PaymentMethodType, PaymentStatus, ProviderName

_JSON = JSON().with_variant(JSONB(), "postgresql")


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        # A provider's reference is unique within that provider.
        UniqueConstraint("provider", "provider_reference", name="provider_reference"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[ProviderName] = mapped_column(
        Enum(ProviderName, native_enum=False, length=40), index=True, nullable=False
    )
    #: Identifier assigned by the downstream provider (nullable until created).
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount_captured: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    amount_refunded: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=40),
        default=PaymentStatus.REQUIRES_CONFIRMATION,
        index=True,
        nullable=False,
    )
    capture_method: Mapped[CaptureMethod] = mapped_column(
        Enum(CaptureMethod, native_enum=False, length=20),
        default=CaptureMethod.AUTOMATIC,
        nullable=False,
    )
    method_type: Mapped[PaymentMethodType] = mapped_column(
        Enum(PaymentMethodType, native_enum=False, length=30),
        default=PaymentMethodType.CARD,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_metadata: Mapped[dict] = mapped_column(_JSON, default=dict, nullable=False)

    refunds: Mapped[list["Refund"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def amount_refundable(self) -> int:
        """Minor units still eligible for refund."""
        return max(0, self.amount_captured - self.amount_refunded)


from app.db.models.refund import Refund  # noqa: E402  (resolve forward relationship)
