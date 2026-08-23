"""Audit service — records security-relevant events to the append-only log."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import correlation_id_var, get_logger
from app.db.models.audit_log import AuditLog
from app.domain.enums import AuditAction
from app.repositories.audit import AuditRepository

_log = get_logger("audit")


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    def record(
        self,
        action: AuditAction,
        *,
        actor_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id_var.get() or None,
            context=context or {},
        )
        self._repo.add(entry)
        _log.info(
            "audit", action=action.value, resource_type=resource_type, resource_id=resource_id
        )
        return entry
