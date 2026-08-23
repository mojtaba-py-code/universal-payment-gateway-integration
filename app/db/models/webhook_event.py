"""Inbound webhook event model.

Every received webhook is persisted first (with its raw body and a per-provider
``event_id``) so processing is idempotent and auditable, and so failed events
can be retried or dead-lettered.
"""

from __future__ import annotations

from sqlalchemy import Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domain.enums import ProviderName, WebhookStatus

_JSON = JSON().with_variant(JSONB(), "postgresql")


class WebhookEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        # Deduplicate on (provider, event_id): the idempotency guarantee.
        UniqueConstraint("provider", "event_id", name="provider_event_id"),
    )

    provider: Mapped[ProviderName] = mapped_column(
        Enum(ProviderName, native_enum=False, length=40), index=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus, native_enum=False, length=20),
        default=WebhookStatus.RECEIVED,
        index=True,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(_JSON, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
