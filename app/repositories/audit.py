"""Audit-log repository and provider-config repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.provider_config import ProviderConfig
from app.domain.enums import ProviderName
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog


class ProviderConfigRepository(BaseRepository[ProviderConfig]):
    model = ProviderConfig

    async def get_active(
        self, owner_id: uuid.UUID, provider: ProviderName
    ) -> ProviderConfig | None:
        result = await self.session.execute(
            select(ProviderConfig).where(
                ProviderConfig.owner_id == owner_id,
                ProviderConfig.provider == provider,
                ProviderConfig.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
