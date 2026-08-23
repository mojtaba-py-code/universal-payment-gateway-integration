"""Payment status state machine.

Centralising the allowed transitions makes the payment lifecycle auditable and
prevents illegal jumps (e.g. refunding a payment that was only authorized). The
service layer consults :func:`assert_transition` before persisting any change.
"""

from __future__ import annotations

from app.core.errors import InvalidStateError
from app.domain.enums import PaymentStatus

# Directed graph of permitted transitions.
_ALLOWED: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.REQUIRES_CONFIRMATION: frozenset(
        {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
            PaymentStatus.CANCELED,
            PaymentStatus.FAILED,
        }
    ),
    PaymentStatus.AUTHORIZED: frozenset(
        {PaymentStatus.CAPTURED, PaymentStatus.CANCELED, PaymentStatus.FAILED}
    ),
    PaymentStatus.CAPTURED: frozenset({PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}),
    PaymentStatus.PARTIALLY_REFUNDED: frozenset(
        {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
    ),
    PaymentStatus.REFUNDED: frozenset(),
    PaymentStatus.CANCELED: frozenset(),
    PaymentStatus.FAILED: frozenset(),
}

TERMINAL_STATES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.REFUNDED, PaymentStatus.CANCELED, PaymentStatus.FAILED}
)


def can_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in _ALLOWED.get(current, frozenset())


def assert_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    """Raise :class:`InvalidStateError` if the transition is not permitted."""
    if not can_transition(current, target):
        raise InvalidStateError(
            f"illegal payment transition {current.value} -> {target.value}",
            details={"from": current.value, "to": target.value},
        )
