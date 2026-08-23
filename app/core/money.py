"""Money value object.

Payments must never use binary floating point. This module models monetary
amounts as an integer number of *minor units* (e.g. cents) plus an ISO-4217
currency code, which is exactly how every serious payment provider represents
amounts on the wire. All arithmetic is exact and currency-checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

# ISO-4217 subset with the number of decimal places (exponent) each currency
# uses. Extend freely — the value object works for any registered currency.
CURRENCY_EXPONENTS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CAD": 2,
    "AUD": 2,
    "TRY": 2,
    "AED": 2,
    "SAR": 2,
    "INR": 2,
    "JPY": 0,  # yen has no minor unit
    "BTC": 8,
    "ETH": 8,
    "USDT": 6,
}


class CurrencyError(ValueError):
    """Raised for unknown currencies or cross-currency operations."""


def is_supported_currency(code: str) -> bool:
    return code.upper() in CURRENCY_EXPONENTS


def exponent_for(currency: str) -> int:
    try:
        return CURRENCY_EXPONENTS[currency.upper()]
    except KeyError as exc:  # pragma: no cover - trivial
        raise CurrencyError(f"Unsupported currency: {currency!r}") from exc


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable, exact monetary amount.

    Attributes:
        minor_units: signed integer amount in the currency's smallest unit.
        currency: upper-case ISO-4217 code.
    """

    minor_units: int
    currency: str

    def __post_init__(self) -> None:
        code = self.currency.upper()
        if not is_supported_currency(code):
            raise CurrencyError(f"Unsupported currency: {self.currency!r}")
        # ``frozen`` dataclass: normalise the currency case via object.__setattr__.
        object.__setattr__(self, "currency", code)
        if not isinstance(self.minor_units, int) or isinstance(self.minor_units, bool):
            raise TypeError("minor_units must be an int")

    # -- Constructors ----------------------------------------------------------
    @classmethod
    def from_decimal(cls, amount: Decimal | str | int, currency: str) -> Money:
        """Build from a human-readable major-unit amount (e.g. ``"12.34"``)."""
        exp = exponent_for(currency)
        quantum = Decimal(1).scaleb(-exp)
        scaled = (Decimal(str(amount)) / quantum).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        return cls(int(scaled), currency)

    # -- Conversions -----------------------------------------------------------
    def to_decimal(self) -> Decimal:
        exp = exponent_for(self.currency)
        return (Decimal(self.minor_units) * Decimal(1).scaleb(-exp)).quantize(
            Decimal(1).scaleb(-exp)
        )

    def format(self) -> str:
        """Human-readable string, e.g. ``"12.34 USD"``."""
        return f"{self.to_decimal()} {self.currency}"

    # -- Predicates ------------------------------------------------------------
    @property
    def is_positive(self) -> bool:
        return self.minor_units > 0

    @property
    def is_zero(self) -> bool:
        return self.minor_units == 0

    def _check_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyError(
                f"Cannot operate across currencies: {self.currency} vs {other.currency}"
            )

    # -- Arithmetic ------------------------------------------------------------
    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.minor_units + other.minor_units, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.minor_units - other.minor_units, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.minor_units < other.minor_units

    def __le__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.minor_units <= other.minor_units

    def __gt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.minor_units > other.minor_units

    def __ge__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.minor_units >= other.minor_units

    def __str__(self) -> str:
        return self.format()
