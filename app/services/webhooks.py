"""Webhook service — the webhook engine.

Every inbound webhook is:

1. **Verified** — signature + timestamp (replay protection) via the provider
   adapter.
2. **Deduplicated** — a unique ``(provider, event_id)`` constraint plus an
   explicit lookup make processing idempotent, so a provider re-delivering the
   same event never causes duplicate side effects.
3. **Persisted** — the raw event is stored for audit, retry, and dead-lettering.

Signature/replay failures raise before anything is written, so malicious or
stale deliveries leave no state behind.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.metrics import webhook_events_total
from app.db.models.webhook_event import WebhookEvent
from app.domain.enums import AuditAction, ProviderName, WebhookStatus
from app.providers.base import BasePaymentProvider
from app.repositories.webhooks import WebhookRepository
from app.services.audit import AuditService

_log = get_logger("webhooks")


class WebhookService:
    def __init__(self, *, repo: WebhookRepository, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def handle(
        self,
        *,
        adapter: BasePaymentProvider,
        provider: ProviderName,
        body: bytes,
        headers: dict[str, str],
    ) -> tuple[WebhookEvent, bool]:
        """Verify, deduplicate, and persist an inbound webhook.

        Returns a ``(event, is_duplicate)`` tuple.
        """
        # 1. Verify signature + replay window (raises on failure — nothing persisted).
        try:
            verified = adapter.verify_webhook(body, headers)
        except Exception:
            webhook_events_total.labels(provider=provider.value, outcome="rejected").inc()
            raise

        # 2. Idempotency: return the stored event if we have already seen it.
        existing = await self._repo.get_by_event(provider, verified.event_id)
        if existing is not None:
            webhook_events_total.labels(provider=provider.value, outcome="duplicate").inc()
            _log.info("webhook.duplicate", provider=provider.value, event_id=verified.event_id)
            return existing, True

        # 3. Persist.
        event = WebhookEvent(
            provider=provider,
            event_id=verified.event_id,
            event_type=verified.event_type,
            status=WebhookStatus.PROCESSED,
            payload=verified.payload,
            attempts=1,
        )
        self._repo.add(event)
        await self._repo.flush()
        webhook_events_total.labels(provider=provider.value, outcome="processed").inc()
        self._audit.record(
            AuditAction.WEBHOOK_RECEIVED,
            resource_type="webhook",
            resource_id=verified.event_id,
            context={"provider": provider.value, "type": verified.event_type},
        )
        return event, False
