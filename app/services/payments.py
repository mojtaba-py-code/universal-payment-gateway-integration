"""Payment service — the transaction engine.

Coordinates the persistence of payments with provider operations, enforcing the
payment state machine on every transition and emitting audit + metric events.
The service is provider-agnostic: it only speaks the unified DTOs exposed by the
:class:`GatewayManager`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.errors import InvalidStateError, ValidationError
from app.core.metrics import payment_operations_total
from app.core.money import Money
from app.db.models.payment import Payment
from app.db.models.user import User
from app.domain.enums import (
    AuditAction,
    CaptureMethod,
    PaymentMethodType,
    PaymentStatus,
    ProviderName,
)
from app.domain.state_machine import assert_transition
from app.providers.base import ChargeRequest
from app.repositories.audit import ProviderConfigRepository
from app.repositories.payments import PaymentRepository
from app.services.audit import AuditService
from app.services.gateway_manager import GatewayManager


class PaymentService:
    def __init__(
        self,
        *,
        payments: PaymentRepository,
        provider_configs: ProviderConfigRepository,
        gateway: GatewayManager,
        audit: AuditService,
    ) -> None:
        self._payments = payments
        self._provider_configs = provider_configs
        self._gateway = gateway
        self._audit = audit

    # -- Create ----------------------------------------------------------------
    async def create_payment(
        self,
        *,
        owner: User,
        provider: ProviderName,
        amount: Money,
        capture_method: CaptureMethod = CaptureMethod.AUTOMATIC,
        method_type: PaymentMethodType = PaymentMethodType.CARD,
        payment_method_token: str | None = None,
        description: str | None = None,
        customer_reference: str | None = None,
        metadata: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Payment:
        if not amount.is_positive:
            raise ValidationError("amount must be greater than zero")

        payment = Payment(
            owner_id=owner.id,
            provider=provider,
            amount=amount.minor_units,
            currency=amount.currency,
            status=PaymentStatus.REQUIRES_CONFIRMATION,
            capture_method=capture_method,
            method_type=method_type,
            description=description,
            customer_reference=customer_reference,
            payment_metadata=metadata or {},
        )
        self._payments.add(payment)
        await self._payments.flush()

        adapter = await self._gateway.get_provider(self._provider_configs, owner.id, provider)
        request = ChargeRequest(
            amount=amount,
            capture_method=capture_method,
            method_type=method_type,
            payment_method_token=payment_method_token,
            description=description,
            customer_reference=customer_reference,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
        )
        charge = await self._gateway.execute(provider, lambda: adapter.create_payment(request))

        payment.provider_reference = charge.reference
        assert_transition(payment.status, charge.status)
        payment.status = charge.status
        if charge.status == PaymentStatus.CAPTURED:
            payment.amount_captured = charge.amount_captured
            action = AuditAction.PAYMENT_CAPTURED
            outcome = "captured"
        elif charge.status == PaymentStatus.AUTHORIZED:
            action = AuditAction.PAYMENT_AUTHORIZED
            outcome = "authorized"
        else:  # FAILED
            payment.failure_reason = charge.failure_reason
            action = AuditAction.PAYMENT_FAILED
            outcome = "failed"

        payment_operations_total.labels(
            operation="create", provider=provider.value, outcome=outcome
        ).inc()
        self._audit.record(
            action, actor_id=owner.id, resource_type="payment", resource_id=str(payment.id)
        )
        return payment

    # -- Capture ---------------------------------------------------------------
    async def capture_payment(
        self, *, owner: User, payment_id: uuid.UUID, amount: Money | None = None
    ) -> Payment:
        payment = await self._require_payment(owner, payment_id)
        if payment.status != PaymentStatus.AUTHORIZED:
            raise InvalidStateError(
                "only authorized payments can be captured",
                details={"status": payment.status.value},
            )
        capture_amount = amount or Money(payment.amount, payment.currency)
        if capture_amount.currency != payment.currency:
            raise ValidationError("capture currency mismatch")
        if capture_amount.minor_units > payment.amount:
            raise ValidationError("capture amount exceeds authorized amount")

        adapter = await self._gateway.get_provider(
            self._provider_configs, owner.id, payment.provider
        )
        charge = await self._gateway.execute(
            payment.provider,
            lambda: adapter.capture(payment.provider_reference or "", capture_amount),
        )
        assert_transition(payment.status, PaymentStatus.CAPTURED)
        payment.status = PaymentStatus.CAPTURED
        payment.amount_captured = charge.amount_captured or capture_amount.minor_units
        payment_operations_total.labels(
            operation="capture", provider=payment.provider.value, outcome="captured"
        ).inc()
        self._audit.record(
            AuditAction.PAYMENT_CAPTURED,
            actor_id=owner.id,
            resource_type="payment",
            resource_id=str(payment.id),
        )
        return payment

    # -- Cancel ----------------------------------------------------------------
    async def cancel_payment(self, *, owner: User, payment_id: uuid.UUID) -> Payment:
        payment = await self._require_payment(owner, payment_id)
        assert_transition(payment.status, PaymentStatus.CANCELED)
        adapter = await self._gateway.get_provider(
            self._provider_configs, owner.id, payment.provider
        )
        await self._gateway.execute(
            payment.provider, lambda: adapter.cancel(payment.provider_reference or "")
        )
        payment.status = PaymentStatus.CANCELED
        payment_operations_total.labels(
            operation="cancel", provider=payment.provider.value, outcome="canceled"
        ).inc()
        self._audit.record(
            AuditAction.PAYMENT_CANCELED,
            actor_id=owner.id,
            resource_type="payment",
            resource_id=str(payment.id),
        )
        return payment

    # -- Queries ---------------------------------------------------------------
    async def get_payment(self, owner: User, payment_id: uuid.UUID) -> Payment:
        return await self._require_payment(owner, payment_id)

    async def list_payments(
        self,
        owner: User,
        *,
        status: PaymentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Payment], int]:
        return await self._payments.list_for_owner(
            owner.id, status=status, limit=limit, offset=offset
        )

    async def _require_payment(self, owner: User, payment_id: uuid.UUID) -> Payment:
        from app.core.errors import NotFoundError

        payment = await self._payments.get_for_owner(payment_id, owner.id)
        if payment is None:
            raise NotFoundError("payment not found")
        return payment
