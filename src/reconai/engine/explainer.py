"""Deterministic discrepancy explainer producing auditable financial rationales."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from reconai.engine.financial import format_currency
from reconai.engine.models import DiscrepancyCategory, ReconciliationItem


def explain_discrepancy(
    category: DiscrepancyCategory,
    tx_id: Optional[str],
    settle_id: Optional[str],
    tx_date_str: Optional[str],
    settle_date_str: Optional[str],
    expected_amount: Decimal,
    actual_amount: Decimal,
    difference: Decimal,
    tx_gross: Optional[Decimal] = None,
    tx_fee: Optional[Decimal] = None,
    settle_fee: Optional[Decimal] = None,
    ref_id: Optional[str] = None,
    bank_batch_id: Optional[str] = None,
) -> tuple[str, str]:
    """Generate deterministic, human-readable reason and recommended action for a discrepancy.

    Returns:
        (reason, recommended_action)
    """
    diff_str = format_currency(difference)
    exp_str = format_currency(expected_amount)
    act_str = format_currency(actual_amount)

    if category == DiscrepancyCategory.MATCHED:
        reason = (
            f"Transaction {tx_id} perfectly reconciled against bank settlement {settle_id}. "
            f"Net amount {exp_str} matches settlement date {settle_date_str} with $0.00 variance."
        )
        action = "No action required. Record marked as fully settled."

    elif category == DiscrepancyCategory.TIMING_DIFFERENCE:
        reason = (
            f"Timing difference: Transaction {tx_id} was booked on {tx_date_str}, but bank settlement "
            f"{settle_id} cleared on {settle_date_str} in the subsequent calendar month. "
            f"Expected {exp_str} was settled in full ({act_str}), but crosses accounting cut-off."
        )
        action = (
            "Accrue as 'Settlements in Transit' on the balance sheet for period-end reconciliation. "
            "Do not treat as missing revenue or write-off."
        )

    elif category == DiscrepancyCategory.ROUNDING_DIFFERENCE:
        fee_diff = (
            format_currency(tx_fee - settle_fee)
            if tx_fee is not None and settle_fee is not None
            else diff_str
        )
        reason = (
            f"Fee rounding discrepancy: Gross amounts match ({format_currency(tx_gross)}), but net settlement "
            f"differs by {diff_str} (Expected {exp_str} vs Actual {act_str}). "
            f"Platform deducted per-transaction rounded fee of {format_currency(tx_fee)}, while acquiring bank "
            f"settled with fee of {format_currency(settle_fee)} (fee variance: {fee_diff}) due to aggregate fee rounding."
        )
        action = (
            f"Book {diff_str} to 'Payment Processing Fee Rounding Adjustment'. "
            "Configure acquiring processor settings to synchronize rounding rules (per-transaction vs aggregate batch)."
        )

    elif category == DiscrepancyCategory.DUPLICATE_ENTRY:
        reason = (
            f"Duplicate settlement detected: Settlement record {settle_id} duplicates transaction {tx_id} "
            f"for amount {act_str}. Duplicate records are isolated by ReconAI to prevent inflating bank settlement totals."
        )
        action = (
            "Quarantine duplicate settlement. Review acquiring bank transmission logs to confirm whether this "
            "was a redundant file ingestion/webhook retry or an actual duplicate funds transfer."
        )

    elif category == DiscrepancyCategory.ORPHAN_REFUND:
        ref_text = f"'{ref_id}'" if ref_id else "nonexistent/missing reference"
        reason = (
            f"Orphan refund: Refund {tx_id} for {exp_str} was issued referencing parent transaction {ref_text}, "
            "which cannot be found in the platform transaction ledger."
        )
        action = (
            "Hold settlement and audit refund authorization. Investigate whether the original payment occurred in an "
            "unsupported legacy system, was processed outside the platform, or indicates fraudulent refund injection."
        )

    elif category == DiscrepancyCategory.UNMATCHED_TRANSACTION:
        reason = (
            f"Unmatched platform transaction: Transaction {tx_id} was recorded as SUCCESS on {tx_date_str} "
            f"for net {exp_str}, but no corresponding settlement record exists in the bank file."
        )
        action = (
            "Investigate acquiring gateway batch status. Check if transaction capture failed, funds are held in reserve, "
            "or the settlement file was truncated."
        )

    elif category == DiscrepancyCategory.UNMATCHED_SETTLEMENT:
        reason = (
            f"Unmatched bank settlement: Bank settlement {settle_id} cleared {act_str} on {settle_date_str} "
            f"referencing transaction '{tx_id}', but no corresponding transaction exists in the platform ledger."
        )
        action = (
            "Verify settlement source with treasury/finance. Check if settlement represents a manual wire credit, "
            "monthly merchant account fee credit, or off-ledger refund reversal."
        )

    else:
        reason = f"Unclassified discrepancy for item {tx_id or settle_id}. Variance: {diff_str}."
        action = "Review manually in data explorer."

    return reason, action
