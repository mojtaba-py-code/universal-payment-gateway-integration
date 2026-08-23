"""Tests for retry and circuit breaker (deterministic, no real sleeping)."""

from __future__ import annotations

import pytest
from app.core.errors import CircuitOpenError, ProviderError, ProviderUnavailableError
from app.core.resilience import CircuitBreaker, CircuitState, RetryPolicy, retry_async


async def _noop_sleep(_: float) -> None:
    return None


async def test_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ProviderUnavailableError("boom")
        return "ok"

    result = await retry_async(
        flaky,
        policy=RetryPolicy(max_attempts=3),
        retry_on=(ProviderUnavailableError,),
        sleep=_noop_sleep,
    )
    assert result == "ok"
    assert attempts["n"] == 3


async def test_retry_exhausts_and_raises() -> None:
    async def always_fail() -> None:
        raise ProviderUnavailableError("down")

    with pytest.raises(ProviderUnavailableError):
        await retry_async(
            always_fail,
            policy=RetryPolicy(max_attempts=2),
            retry_on=(ProviderUnavailableError,),
            sleep=_noop_sleep,
        )


def test_retry_delay_is_bounded() -> None:
    policy = RetryPolicy(base_delay=1, max_delay=4, multiplier=2)
    for attempt in range(1, 6):
        assert 0 <= policy.delay_for(attempt) <= 4


async def test_circuit_breaker_opens_after_threshold() -> None:
    clock = {"t": 0.0}
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=10, now=lambda: clock["t"])

    async def fail() -> None:
        raise ProviderUnavailableError("x")

    for _ in range(2):
        with pytest.raises(ProviderUnavailableError):
            await breaker.call(fail)
    assert breaker.state == CircuitState.OPEN

    # While open, calls fail fast without invoking the function.
    with pytest.raises(CircuitOpenError):
        await breaker.call(fail)


async def test_circuit_breaker_half_open_recovers() -> None:
    clock = {"t": 0.0}
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10, now=lambda: clock["t"])

    async def fail() -> None:
        raise ProviderUnavailableError("x")

    async def ok() -> str:
        return "ok"

    with pytest.raises(ProviderUnavailableError):
        await breaker.call(fail)
    assert breaker.state == CircuitState.OPEN

    clock["t"] = 20.0  # cool-off elapsed -> half-open probe allowed
    assert await breaker.call(ok) == "ok"
    assert breaker.state == CircuitState.CLOSED


async def test_circuit_breaker_ignores_business_errors() -> None:
    breaker = CircuitBreaker(failure_threshold=1, ignored_exceptions=(ProviderError,))

    async def declined() -> None:
        raise ProviderError("card_declined")

    # A decline should not trip the breaker.
    for _ in range(5):
        with pytest.raises(ProviderError):
            await breaker.call(declined)
    assert breaker.state == CircuitState.CLOSED
