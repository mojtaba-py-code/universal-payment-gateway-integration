"""Webhook event repository."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models.webhook_event import WebhookEvent
from app.domain.enums import ProviderName
from app.repositories.base import BaseRepository


class WebhookRepository(BaseRepository[WebhookEvent]):
    model = WebhookEvent

    async def get_by_event(self, provider: ProviderName, event_id: str) -> WebhookEvent | None:
        result = await self.session.execute(
            select(WebhookEvent).where(
                WebhookEvent.provider == provider, WebhookEvent.event_id == event_id
            )
        )
        return result.scalar_one_or_none()
