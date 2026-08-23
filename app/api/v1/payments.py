"""Payment endpoints: create, list, retrieve, capture, cancel.

Unsafe operations honour the ``Idempotency-Key`` header so clients can safely
retry after a network failure without double-charging.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import get_idempotency_service, get_payment_service, require_scope
from app.core.money import Money
from app.db.models.user import User
from app.domain.enums import PaymentStatus
from app.domain.rbac import SCOPE_PAYMENTS_READ, SCOPE_PAYMENTS_WRITE
from app.schemas.common import Page, PageMeta
from app.schemas.payment import (
    CapturePaymentRequest,
    CreatePaymentRequest,
    PaymentResponse,
    payment_to_response,
)
from app.services.idempotency import IdempotencyService
from app.services.payments import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])

PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
IdempotencyDep = Annotated[IdempotencyService, Depends(get_idempotency_service)]
WriteUser = Annotated[User, Depends(require_scope(SCOPE_PAYMENTS_WRITE))]
ReadUser = Annotated[User, Depends(require_scope(SCOPE_PAYMENTS_READ))]

_CREATE_ENDPOINT = "create_payment"


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment",
)
async def create_payment(
    payload: CreatePaymentRequest,
    request: Request,
    user: WriteUser,
    service: PaymentServiceDep,
    idempotency: IdempotencyDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    body = payload.model_dump(mode="json")

    if idempotency_key:
        cached = await idempotency.lookup(user.id, _CREATE_ENDPOINT, idempotency_key, body)
        if cached is not None:
            return JSONResponse(cached.body, status_code=cached.status)

    amount = Money(payload.amount_minor, payload.currency)
    payment = await service.create_payment(
        owner=user,
        provider=payload.provider,
        amount=amount,
        capture_method=payload.capture_method,
        method_type=payload.method_type,
        payment_method_token=payload.payment_method_token,
        description=payload.description,
        customer_reference=payload.customer_reference,
        metadata=payload.metadata,
        idempotency_key=idempotency_key,
    )
    response_body = payment_to_response(payment).model_dump(mode="json")

    if idempotency_key:
        await idempotency.store(
            user.id, _CREATE_ENDPOINT, idempotency_key, body, status.HTTP_201_CREATED, response_body
        )
    return JSONResponse(response_body, status_code=status.HTTP_201_CREATED)


@router.get("", response_model=Page[PaymentResponse], summary="List payments")
async def list_payments(
    user: ReadUser,
    service: PaymentServiceDep,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PaymentResponse]:
    items, total = await service.list_payments(
        user, status=status_filter, limit=limit, offset=offset
    )
    return Page[PaymentResponse](
        items=[payment_to_response(p) for p in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{payment_id}", response_model=PaymentResponse, summary="Retrieve a payment")
async def get_payment(
    payment_id: uuid.UUID, user: ReadUser, service: PaymentServiceDep
) -> PaymentResponse:
    payment = await service.get_payment(user, payment_id)
    return payment_to_response(payment)


@router.post(
    "/{payment_id}/capture", response_model=PaymentResponse, summary="Capture an authorized payment"
)
async def capture_payment(
    payment_id: uuid.UUID,
    payload: CapturePaymentRequest,
    user: WriteUser,
    service: PaymentServiceDep,
) -> PaymentResponse:
    payment = await service.get_payment(user, payment_id)
    amount = (
        Money(payload.amount_minor, payment.currency) if payload.amount_minor is not None else None
    )
    updated = await service.capture_payment(owner=user, payment_id=payment_id, amount=amount)
    return payment_to_response(updated)


@router.post(
    "/{payment_id}/cancel", response_model=PaymentResponse, summary="Cancel/void a payment"
)
async def cancel_payment(
    payment_id: uuid.UUID, user: WriteUser, service: PaymentServiceDep
) -> PaymentResponse:
    updated = await service.cancel_payment(owner=user, payment_id=payment_id)
    return payment_to_response(updated)
