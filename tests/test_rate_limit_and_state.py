"""Tests for the in-memory rate limiter and payment state machine."""

from __future__ import annotations

import pytest
from app.core.errors import InvalidStateError
from app.core.rate_limit import InMemoryRateLimiter
from app.domain.enums import PaymentStatus
from app.domain.state_machine import assert_transition, can_transition


def test_rate_limiter_allows_within_limit() -> None:
    clock = {"t": 0.0}
    limiter = InMemoryRateLimiter(limit=3, window_seconds=60, now=lambda: clock["t"])
    results = [limiter.hit("k") for _ in range(3)]
    assert all(r.allowed for r in results)
    assert results[-1].remaining == 0


def test_rate_limiter_blocks_over_limit() -> None:
    clock = {"t": 0.0}
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60, now=lambda: clock["t"])
    limiter.hit("k")
    limiter.hit("k")
    blocked = limiter.hit("k")
    assert not blocked.allowed
    assert blocked.retry_after > 0


def test_rate_limiter_resets_after_window() -> None:
    clock = {"t": 0.0}
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, now=lambda: clock["t"])
    assert limiter.hit("k").allowed
    assert not limiter.hit("k").allowed
    clock["t"] = 61.0
    assert limiter.hit("k").allowed


def test_rate_limiter_separate_keys() -> None:
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    assert limiter.hit("a").allowed
    assert limiter.hit("b").allowed


def test_state_machine_valid_transitions() -> None:
    assert can_transition(PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)
    assert can_transition(PaymentStatus.CAPTURED, PaymentStatus.REFUNDED)
    assert can_transition(PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED)


def test_state_machine_invalid_transition_raises() -> None:
    with pytest.raises(InvalidStateError):
        assert_transition(PaymentStatus.CAPTURED, PaymentStatus.AUTHORIZED)
    with pytest.raises(InvalidStateError):
        assert_transition(PaymentStatus.REFUNDED, PaymentStatus.CAPTURED)
