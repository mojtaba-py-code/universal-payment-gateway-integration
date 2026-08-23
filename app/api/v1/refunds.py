"""Refund endpoints (nested under a payment)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import get_idempotency_service, get_refund_service, require_scope
from app.db.models.user import User
from app.domain.rbac import SCOPE_REFUNDS_WRITE
from app.schemas.payment import CreateRefundRequest, RefundResponse, refund_to_response
from app.services.idempotency import IdempotencyService
from app.services.refunds import RefundService

router = APIRouter(prefix="/payments/{payment_id}/refunds", tags=["refunds"])

RefundServiceDep = Annotated[RefundService, Depends(get_refund_service)]
IdempotencyDep = Annotated[IdempotencyService, Depends(get_idempotency_service)]
RefundUser = Annotated[User, Depends(require_scope(SCOPE_REFUNDS_WRITE))]

_ENDPOINT = "create_refund"


@router.post(
    "",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Refund a payment",
)
async def create_refund(
    payment_id: uuid.UUID,
    payload: CreateRefundRequest,
    request: Request,
    user: RefundUser,
    service: RefundServiceDep,
    idempotency: IdempotencyDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    body = {"payment_id": str(payment_id), **payload.model_dump(mode="json")}

    if idempotency_key:
        cached = await idempotency.lookup(user.id, _ENDPOINT, idempotency_key, body)
        if cached is not None:
            return JSONResponse(cached.body, status_code=cached.status)

    refund = await service.create_refund(
        owner=user,
        payment_id=payment_id,
        amount_minor=payload.amount_minor,
        reason=payload.reason,
    )
    response_body = refund_to_response(refund).model_dump(mode="json")

    if idempotency_key:
        await idempotency.store(
            user.id, _ENDPOINT, idempotency_key, body, status.HTTP_201_CREATED, response_body
        )
    return JSONResponse(response_body, status_code=status.HTTP_201_CREATED)
