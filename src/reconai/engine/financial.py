"""Financial calculations and Decimal precision utilities."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Iterable, List, Tuple


PENNY = Decimal("0.01")
ZERO = Decimal("0.00")

# Standard payment processing fee rates (e.g. 2.9% + $0.30 fixed)
DEFAULT_FEE_RATE = Decimal("0.029")
DEFAULT_FIXED_FEE = Decimal("0.30")


def to_decimal(val: Any) -> Decimal:
    """Convert any numeric, string, or decimal value to a 2-decimal place Decimal.

    Uses ROUND_HALF_UP (standard financial rounding convention).
    """
    if val is None:
        return ZERO

    if isinstance(val, Decimal):
        return val.quantize(PENNY, rounding=ROUND_HALF_UP)

    try:
        # Strip common formatting like currency symbols, commas, whitespace
        cleaned = str(val).strip().replace("$", "").replace(",", "")
        if not cleaned:
            return ZERO
        d = Decimal(cleaned)
        return d.quantize(PENNY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Cannot convert value '{val}' to financial Decimal: {exc}") from exc


def calculate_per_transaction_fee(
    gross_amount: Decimal,
    fee_rate: Decimal = DEFAULT_FEE_RATE,
    fixed_fee: Decimal = DEFAULT_FIXED_FEE,
) -> Decimal:
    """Calculate the processing fee for an individual transaction with per-transaction rounding.

    Formula: round(gross * fee_rate + fixed_fee, 2)
    For negative amounts (refunds), fee is typically 0 or minimal.
    """
    if gross_amount <= ZERO:
        return ZERO

    raw_fee = (gross_amount * fee_rate) + fixed_fee
    return raw_fee.quantize(PENNY, rounding=ROUND_HALF_UP)


def calculate_aggregate_fee(
    gross_amounts: Iterable[Decimal],
    fee_rate: Decimal = DEFAULT_FEE_RATE,
    fixed_fee: Decimal = DEFAULT_FIXED_FEE,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculate aggregate fee vs sum of per-transaction fees across a batch.

    Returns:
        (sum_per_tx_fees, aggregate_fee, rounding_difference)
        where rounding_difference = sum_per_tx_fees - aggregate_fee.
    """
    amounts_list = [to_decimal(a) for a in gross_amounts if to_decimal(a) > ZERO]
    if not amounts_list:
        return ZERO, ZERO, ZERO

    total_gross = sum(amounts_list, ZERO)
    count = Decimal(len(amounts_list))

    # 1. Sum of individually rounded per-transaction fees
    sum_per_tx_fees = sum(
        (calculate_per_transaction_fee(a, fee_rate, fixed_fee) for a in amounts_list),
        ZERO
    )

    # 2. Aggregate fee rounded once at batch level
    raw_aggregate_fee = (total_gross * fee_rate) + (count * fixed_fee)
    aggregate_fee = raw_aggregate_fee.quantize(PENNY, rounding=ROUND_HALF_UP)

    # 3. Rounding difference
    rounding_difference = (sum_per_tx_fees - aggregate_fee).quantize(PENNY, rounding=ROUND_HALF_UP)

    return sum_per_tx_fees, aggregate_fee, rounding_difference


def calculate_net_amount(gross_amount: Decimal, fee_amount: Decimal, is_refund: bool = False) -> Decimal:
    """Calculate net amount ensuring Decimal integrity.

    For payments: net = gross - fee (positive inflow)
    For refunds: net = gross + fee (e.g. -$50.00 + $0.00 = -$50.00 outflow)
    """
    gross = to_decimal(gross_amount)
    fee = to_decimal(fee_amount)

    if is_refund or gross < ZERO:
        # Gross is negative, fee reduces platform cost or is 0
        return (gross + fee).quantize(PENNY, rounding=ROUND_HALF_UP)
    return (gross - fee).quantize(PENNY, rounding=ROUND_HALF_UP)


def format_currency(val: Decimal | None) -> str:
    """Format Decimal into USD currency string e.g. '$1,234.56' or '($50.00)'."""
    if val is None:
        return "$0.00"
    dec = to_decimal(val)
    if dec < ZERO:
        return f"-${abs(dec):,.2f}"
    return f"${dec:,.2f}"
