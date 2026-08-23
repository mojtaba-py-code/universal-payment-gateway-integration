"""Append-only audit log.

Security-relevant actions (auth, key management, payment mutations) are recorded
with the actor, a stable action code, the target resource, and structured
context. Rows are never updated or deleted in normal operation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domain.enums import AuditAction

_JSON = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, length=60), index=True, nullable=False
    )
    resource_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context: Mapped[dict] = mapped_column(_JSON, default=dict, nullable=False)
