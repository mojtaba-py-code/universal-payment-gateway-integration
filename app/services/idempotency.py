"""Idempotency service.

Guarantees at-most-once semantics for unsafe operations. A client supplies an
``Idempotency-Key`` header; the first request executes and its response is
persisted, and any retry with the *same* key returns the stored response without
re-executing. A retry that reuses the key with a *different* body is a client
error (:class:`IdempotencyConflictError`).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from app.core.errors import IdempotencyConflictError
from app.db.models.idempotency import IdempotencyKey
from app.repositories.idempotency import IdempotencyRepository


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status: int
    body: dict


def _hash_body(body: dict) -> str:
    canonical = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class IdempotencyService:
    def __init__(self, repo: IdempotencyRepository) -> None:
        self._repo = repo

    async def lookup(
        self, owner_id: uuid.UUID, endpoint: str, key: str, request_body: dict
    ) -> StoredResponse | None:
        record = await self._repo.get(owner_id, endpoint, key)
        if record is None:
            return None
        if record.request_hash != _hash_body(request_body):
            raise IdempotencyConflictError(
                "idempotency key reused with a different request body",
                details={"key": key},
            )
        return StoredResponse(status=record.response_status, body=record.response_body)

    async def store(
        self,
        owner_id: uuid.UUID,
        endpoint: str,
        key: str,
        request_body: dict,
        status: int,
        response_body: dict,
    ) -> None:
        record = IdempotencyKey(
            owner_id=owner_id,
            endpoint=endpoint,
            key=key,
            request_hash=_hash_body(request_body),
            response_status=status,
            response_body=response_body,
        )
        self._repo.add(record)
        await self._repo.flush()
