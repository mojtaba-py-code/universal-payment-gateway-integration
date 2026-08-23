"""Inbound webhook endpoint.

This endpoint is intentionally unauthenticated (providers call it directly);
trust is established by verifying the cryptographic signature on the raw request
body, not by a bearer token. The raw body is read verbatim — re-serialising it
would break signature verification.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.api.deps import SessionDep, get_gateway_manager, get_webhook_service
from app.domain.enums import ProviderName
from app.repositories.audit import ProviderConfigRepository
from app.services.gateway_manager import GatewayManager
from app.services.webhooks import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookAck(BaseModel):
    received: bool
    duplicate: bool
    event_id: str
    event_type: str


@router.post("/{provider}", response_model=WebhookAck, summary="Receive a provider webhook")
async def receive_webhook(
    provider: ProviderName,
    request: Request,
    session: SessionDep,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
    gateway: Annotated[GatewayManager, Depends(get_gateway_manager)],
    account_id: Annotated[str | None, Header(alias="X-UPGI-Account")] = None,
) -> WebhookAck:
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    # Resolve the adapter that holds the correct signing secret for verification.
    owner_id = uuid.UUID(account_id) if account_id else uuid.uuid4()
    adapter = await gateway.get_provider(ProviderConfigRepository(session), owner_id, provider)

    event, duplicate = await service.handle(
        adapter=adapter, provider=provider, body=raw_body, headers=headers
    )
    return WebhookAck(
        received=True,
        duplicate=duplicate,
        event_id=event.event_id,
        event_type=event.event_type,
    )
