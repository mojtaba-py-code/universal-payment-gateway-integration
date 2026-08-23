"""Idempotency key model.

Clients send an ``Idempotency-Key`` header on unsafe operations (create payment,
refund). We persist the key scoped to the owner together with a hash of the
request body and the stored response, so a retried request returns the original
result instead of executing twice — while a *different* body under the same key
is rejected as a conflict.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDMixin

_JSON = JSON().with_variant(JSONB(), "postgresql")


class IdempotencyKey(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("owner_id", "endpoint", "key", name="owner_endpoint_key"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    #: SHA-256 of the canonical request body; guards against key reuse with a
    #: different payload.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(_JSON, nullable=False)
