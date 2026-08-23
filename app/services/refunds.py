"""Refund service — the refund engine.

Supports full and partial refunds with a hard invariant: the cumulative refunded
amount can never exceed the captured amount. State transitions
(``captured → partially_refunded → refunded``) go through the shared state
machine.
"""

from __future__ import annotations

import uuid

from app.core.errors import InvalidStateError, NotFoundError, ValidationError
from app.core.metrics import payment_operations_total
from app.core.money import Money
from app.db.models.refund import Refund
from app.db.models.user import User
from app.domain.enums import AuditAction, PaymentStatus, RefundStatus
from app.domain.state_machine import assert_transition
from app.repositories.audit import ProviderConfigRepository
from app.repositories.payments import PaymentRepository
from app.repositories.refunds import RefundRepository
from app.services.audit import AuditService
from app.services.gateway_manager import GatewayManager

_REFUNDABLE_STATES = frozenset({PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED})


class RefundService:
    def __init__(
        self,
        *,
        payments: PaymentRepository,
        refunds: RefundRepository,
        provider_configs: ProviderConfigRepository,
        gateway: GatewayManager,
        audit: AuditService,
    ) -> None:
        self._payments = payments
        self._refunds = refunds
        self._provider_configs = provider_configs
        self._gateway = gateway
        self._audit = audit

    async def create_refund(
        self,
        *,
        owner: User,
        payment_id: uuid.UUID,
        amount_minor: int | None = None,
        reason: str | None = None,
    ) -> Refund:
        payment = await self._payments.get_for_owner(payment_id, owner.id)
        if payment is None:
            raise NotFoundError("payment not found")
        if payment.status not in _REFUNDABLE_STATES:
            raise InvalidStateError(
                "only captured payments can be refunded",
                details={"status": payment.status.value},
            )

        refundable = payment.amount_refundable
        # The refund currency always matches the payment; amount is in minor units.
        refund_amount = Money(
            amount_minor if amount_minor is not None else refundable, payment.currency
        )

        if not refund_amount.is_positive:
            raise ValidationError("refund amount must be greater than zero")
        if refund_amount.minor_units > refundable:
            raise ValidationError(
                "refund amount exceeds refundable balance",
                details={"refundable_minor_units": refundable},
            )

        adapter = await self._gateway.get_provider(
            self._provider_configs, owner.id, payment.provider
        )
        result = await self._gateway.execute(
            payment.provider,
            lambda: adapter.refund(payment.provider_reference or "", refund_amount, reason),
        )

        refund = Refund(
            payment_id=payment.id,
            amount=refund_amount.minor_units,
            currency=payment.currency,
            status=RefundStatus.SUCCEEDED if result.status == "succeeded" else RefundStatus.PENDING,
            reason=reason,
            provider_reference=result.reference,
        )
        self._refunds.add(refund)

        payment.amount_refunded += refund_amount.minor_units
        target = (
            PaymentStatus.REFUNDED
            if payment.amount_refunded >= payment.amount_captured
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        assert_transition(payment.status, target)
        payment.status = target

        await self._refunds.flush()
        payment_operations_total.labels(
            operation="refund", provider=payment.provider.value, outcome="succeeded"
        ).inc()
        self._audit.record(
            AuditAction.REFUND_CREATED,
            actor_id=owner.id,
            resource_type="refund",
            resource_id=str(refund.id),
        )
        return refund
