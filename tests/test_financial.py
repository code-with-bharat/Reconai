"""Tests for Decimal precision and financial calculation logic."""

from decimal import Decimal
import pytest

from reconai.engine.financial import (
    calculate_aggregate_fee,
    calculate_net_amount,
    calculate_per_transaction_fee,
    format_currency,
    to_decimal,
)


def test_to_decimal_precision():
    """Verify conversion to Decimal preserves exact currency cents without float artifacts."""
    assert to_decimal("123.456") == Decimal("123.46")  # ROUND_HALF_UP
    assert to_decimal("$1,234.50") == Decimal("1234.50")
    assert to_decimal(45.5) == Decimal("45.50")
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal("") == Decimal("0.00")


def test_to_decimal_invalid():
    """Verify invalid strings raise ValueError."""
    with pytest.raises(ValueError):
        to_decimal("invalid-money-value")


def test_calculate_per_transaction_fee():
    """Verify standard formula: round(gross * 0.029 + 0.30, 2)."""
    # 100.00 * 0.029 + 0.30 = 3.20
    gross = Decimal("100.00")
    fee = calculate_per_transaction_fee(gross)
    assert fee == Decimal("3.20")

    # Negative / refund amount has zero fee
    assert calculate_per_transaction_fee(Decimal("-50.00")) == Decimal("0.00")


def test_calculate_aggregate_fee_difference():
    """Verify genuine aggregate rounding difference between per-tx fees and batch aggregate fee."""
    amounts = [
        Decimal("45.15"), Decimal("67.89"), Decimal("120.35"), Decimal("89.44"),
        Decimal("15.67"), Decimal("210.50"), Decimal("34.99"), Decimal("78.20")
    ]
    sum_per_tx, agg_fee, diff = calculate_aggregate_fee(amounts)

    assert sum_per_tx == Decimal("21.59")
    assert agg_fee == Decimal("21.60")
    assert diff == Decimal("-0.01")  # Penny variance demonstrates aggregate fee rounding difference


def test_calculate_net_amount():
    """Verify net calculation for payment inflows and refund outflows."""
    # Payment: Net = Gross - Fee
    gross = Decimal("250.00")
    fee = Decimal("7.55")
    assert calculate_net_amount(gross, fee) == Decimal("242.45")

    # Refund: Net = Gross (negative)
    refund_gross = Decimal("-75.00")
    assert calculate_net_amount(refund_gross, Decimal("0.00"), is_refund=True) == Decimal("-75.00")


def test_format_currency():
    """Verify currency formatting with commas and negative signs."""
    assert format_currency(Decimal("1234567.89")) == "$1,234,567.89"
    assert format_currency(Decimal("-50.00")) == "-$50.00"
    assert format_currency(Decimal("0.00")) == "$0.00"
    assert format_currency(None) == "$0.00"
