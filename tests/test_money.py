"""Tests for the Money value object."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.money import CurrencyError, Money, exponent_for, is_supported_currency


def test_from_decimal_rounds_to_minor_units() -> None:
    assert Money.from_decimal("12.34", "USD").minor_units == 1234
    assert Money.from_decimal("12.345", "USD").minor_units == 1234  # banker's rounding
    assert Money.from_decimal("12.355", "USD").minor_units == 1236


def test_zero_decimal_currency() -> None:
    money = Money.from_decimal("1000", "JPY")
    assert money.minor_units == 1000
    assert money.to_decimal() == Decimal("1000")


def test_crypto_precision() -> None:
    assert Money.from_decimal("0.00000001", "BTC").minor_units == 1


def test_format_and_str() -> None:
    money = Money(1234, "usd")
    assert money.currency == "USD"  # normalised
    assert money.format() == "12.34 USD"
    assert str(money) == "12.34 USD"


def test_arithmetic_same_currency() -> None:
    assert (Money(100, "USD") + Money(50, "USD")).minor_units == 150
    assert (Money(100, "USD") - Money(30, "USD")).minor_units == 70


def test_comparison() -> None:
    assert Money(100, "USD") < Money(200, "USD")
    assert Money(200, "USD") >= Money(200, "USD")
    assert Money(50, "USD") <= Money(50, "USD")
    assert Money(300, "USD") > Money(200, "USD")


def test_cross_currency_is_rejected() -> None:
    with pytest.raises(CurrencyError):
        Money(100, "USD") + Money(100, "EUR")
    with pytest.raises(CurrencyError):
        _ = Money(100, "USD") < Money(100, "EUR")


def test_unsupported_currency_rejected() -> None:
    with pytest.raises(CurrencyError):
        Money(100, "XXX")


def test_bool_is_not_valid_minor_units() -> None:
    with pytest.raises(TypeError):
        Money(True, "USD")  # type: ignore[arg-type]


def test_predicates() -> None:
    assert Money(1, "USD").is_positive
    assert Money(0, "USD").is_zero
    assert not Money(-1, "USD").is_positive


def test_helpers() -> None:
    assert is_supported_currency("usd")
    assert not is_supported_currency("xxx")
    assert exponent_for("JPY") == 0
    with pytest.raises(CurrencyError):
        exponent_for("XXX")
