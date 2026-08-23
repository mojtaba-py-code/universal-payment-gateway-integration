"""Per-tenant provider configuration.

Credentials are stored encrypted (AES-256-GCM envelope) in ``encrypted_secret``.
The cleartext never touches the database. ``config`` holds non-secret settings
(e.g. base URL, webhook signing key id) as JSON.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domain.enums import ProviderName

# Use JSONB on PostgreSQL, fall back to generic JSON elsewhere (SQLite in tests).
_JSON = JSON().with_variant(JSONB(), "postgresql")


class ProviderConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "provider_configs"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[ProviderName] = mapped_column(
        Enum(ProviderName, native_enum=False, length=40), nullable=False
    )
    #: AES-256-GCM envelope-encrypted provider secret (base64 token).
    encrypted_secret: Mapped[str] = mapped_column(String(2048), nullable=False)
    #: Non-secret configuration (base_url, sandbox flags, etc.).
    config: Mapped[dict] = mapped_column(_JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
