"""Domain models for ReconAI payment reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional


class DiscrepancyCategory(str, Enum):
    """Reconciliation classification categories."""
    MATCHED = "Matched"
    TIMING_DIFFERENCE = "Timing differences"
    ROUNDING_DIFFERENCE = "Rounding differences"
    DUPLICATE_ENTRY = "Duplicate entries"
    ORPHAN_REFUND = "Orphan refunds"
    UNMATCHED_TRANSACTION = "Unmatched transactions"
    UNMATCHED_SETTLEMENT = "Unmatched settlements"


@dataclass
class Transaction:
    """Internal payment platform ledger record."""
    transaction_id: str
    date: date
    type: str  # PAYMENT, REFUND
    status: str  # SUCCESS, FAILED, PENDING
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    currency: str = "USD"
    customer_id: str = ""
    payment_method: str = "CREDIT_CARD"  # CREDIT_CARD, ACH, DEBIT, WIRE
    reference_id: Optional[str] = None  # Original transaction ID for refunds
    description: str = ""
    raw_row: int = 0


@dataclass
class Settlement:
    """Bank settlement statement record."""
    settlement_id: str
    settlement_date: date
    transaction_id: str
    type: str  # CREDIT, DEBIT
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    currency: str = "USD"
    bank_batch_id: str = ""
    raw_row: int = 0


@dataclass
class ReconciliationItem:
    """Individual item result after reconciliation comparison."""
    item_id: str
    category: DiscrepancyCategory
    transaction_id: Optional[str] = None
    settlement_id: Optional[str] = None
    transaction_date: Optional[date] = None
    settlement_date: Optional[date] = None
    transaction_gross: Optional[Decimal] = None
    transaction_fee: Optional[Decimal] = None
    transaction_net: Optional[Decimal] = None
    settlement_gross: Optional[Decimal] = None
    settlement_fee: Optional[Decimal] = None
    settlement_net: Optional[Decimal] = None
    expected_amount: Decimal = Decimal("0.00")
    actual_amount: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    reason: str = ""
    recommended_action: str = ""
    is_duplicate: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ReconciliationSummary:
    """Overall reconciliation summary and metrics for an accounting period."""
    period_label: str
    target_year: int
    target_month: int

    # Platform Ledger Totals (filtered to target period)
    platform_total_gross: Decimal
    platform_total_fees: Decimal
    platform_total_net: Decimal
    platform_transaction_count: int

    # Bank Settlement Totals (active non-duplicate settlements affecting target period reconciliation)
    bank_total_gross: Decimal
    bank_total_fees: Decimal
    bank_total_net: Decimal
    bank_settlement_count: int
    raw_bank_total_net_with_duplicates: Decimal

    # Reconciliation Metrics
    reconciled_net: Decimal
    discrepancy_net: Decimal
    match_rate_pct: float

    # Category Counts & Breakdown
    counts_by_category: Dict[DiscrepancyCategory, int]
    amounts_by_category: Dict[DiscrepancyCategory, Decimal]
    items: List[ReconciliationItem] = field(default_factory=list)
