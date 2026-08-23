"""Payment & refund schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.money import is_supported_currency

if TYPE_CHECKING:
    from app.db.models.payment import Payment
    from app.db.models.refund import Refund
from app.domain.enums import (
    CaptureMethod,
    PaymentMethodType,
    PaymentStatus,
    ProviderName,
    RefundStatus,
)
from app.schemas.common import MoneyOut


class _CurrencyMixin(BaseModel):
    currency: str = Field(min_length=3, max_length=8, examples=["USD"])

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, value: str) -> str:
        code = value.upper()
        if not is_supported_currency(code):
            raise ValueError(f"unsupported currency {value!r}")
        return code


class CreatePaymentRequest(_CurrencyMixin):
    provider: ProviderName = ProviderName.MOCK
    amount_minor: int = Field(gt=0, le=10**12, description="Amount in the currency's minor units.")
    capture_method: CaptureMethod = CaptureMethod.AUTOMATIC
    method_type: PaymentMethodType = PaymentMethodType.CARD
    payment_method_token: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    customer_reference: str | None = Field(default=None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class CapturePaymentRequest(BaseModel):
    #: Optional partial capture amount; defaults to the full authorized amount.
    amount_minor: int | None = Field(default=None, gt=0, le=10**12)


class CreateRefundRequest(BaseModel):
    #: Optional partial refund amount; defaults to the full refundable balance.
    amount_minor: int | None = Field(default=None, gt=0, le=10**12)
    reason: str | None = Field(default=None, max_length=500)


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_id: uuid.UUID
    amount: MoneyOut
    status: RefundStatus
    reason: str | None
    provider_reference: str | None
    created_at: datetime


class PaymentResponse(BaseModel):
    id: uuid.UUID
    provider: ProviderName
    provider_reference: str | None
    status: PaymentStatus
    capture_method: CaptureMethod
    method_type: PaymentMethodType
    amount: MoneyOut
    amount_captured: MoneyOut
    amount_refunded: MoneyOut
    description: str | None
    customer_reference: str | None
    failure_reason: str | None
    metadata: dict
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Mappers (ORM model -> response schema)                                       #
# --------------------------------------------------------------------------- #
def money_out(minor_units: int, currency: str) -> MoneyOut:
    from app.core.money import Money

    money = Money(minor_units, currency)
    return MoneyOut(minor_units=minor_units, currency=currency, display=money.format())


def payment_to_response(payment: Payment) -> PaymentResponse:
    p = payment
    return PaymentResponse(
        id=p.id,
        provider=p.provider,
        provider_reference=p.provider_reference,
        status=p.status,
        capture_method=p.capture_method,
        method_type=p.method_type,
        amount=money_out(p.amount, p.currency),
        amount_captured=money_out(p.amount_captured, p.currency),
        amount_refunded=money_out(p.amount_refunded, p.currency),
        description=p.description,
        customer_reference=p.customer_reference,
        failure_reason=p.failure_reason,
        metadata=p.payment_metadata,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def refund_to_response(refund: Refund) -> RefundResponse:
    r = refund
    return RefundResponse(
        id=r.id,
        payment_id=r.payment_id,
        amount=money_out(r.amount, r.currency),
        status=r.status,
        reason=r.reason,
        provider_reference=r.provider_reference,
        created_at=r.created_at,
    )
