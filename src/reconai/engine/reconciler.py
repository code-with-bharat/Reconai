"""Deterministic reconciliation engine with Decimal financial precision."""

from __future__ import annotations

import calendar
import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from reconai.engine.explainer import explain_discrepancy
from reconai.engine.financial import (
    PENNY,
    ZERO,
    calculate_net_amount,
    to_decimal,
)
from reconai.engine.models import (
    DiscrepancyCategory,
    ReconciliationItem,
    ReconciliationSummary,
    Settlement,
    Transaction,
)


class ReconciliationEngine:
    """Core reconciliation engine matching ledger transactions with settlement statements."""

    def __init__(
        self,
        transactions: List[Transaction],
        settlements: List[Settlement],
        target_year: int = 2026,
        target_month: int = 11,
        rounding_tolerance: Decimal = Decimal("0.10"),
    ):
        self.all_transactions = transactions
        self.all_settlements = settlements
        self.target_year = target_year
        self.target_month = target_month
        self.rounding_tolerance = rounding_tolerance

        # Period date boundaries
        _, last_day = calendar.monthrange(target_year, target_month)
        self.period_start = datetime.date(target_year, target_month, 1)
        self.period_end = datetime.date(target_year, target_month, last_day)
        self.period_label = f"{target_year}-{target_month:02d}"

    def reconcile(self) -> ReconciliationSummary:
        """Execute full multi-phase reconciliation and compile financial summary."""
        items: List[ReconciliationItem] = []

        # -------------------------------------------------------------
        # Phase 1: Build Lookup Maps
        # -------------------------------------------------------------
        all_tx_by_id: Dict[str, Transaction] = {tx.transaction_id: tx for tx in self.all_transactions}

        # Filter transactions belonging to target accounting period
        target_txs = [
            tx for tx in self.all_transactions
            if tx.date.year == self.target_year and tx.date.month == self.target_month
        ]
        target_tx_by_id: Dict[str, Transaction] = {tx.transaction_id: tx for tx in target_txs}

        # -------------------------------------------------------------
        # Phase 2: Detect & Isolate Duplicate Settlements
        # -------------------------------------------------------------
        # A duplicate can occur if the same settlement_id or same transaction_id
        # appears multiple times in settlements.
        active_settlements_by_tx_id: Dict[str, Settlement] = {}
        duplicate_settlements: List[Settlement] = []
        seen_tx_settlements: Set[str] = set()

        raw_bank_total_net = sum((s.net_amount for s in self.all_settlements), ZERO)

        for stl in self.all_settlements:
            key = stl.transaction_id
            if key in seen_tx_settlements:
                # Duplicate detected!
                duplicate_settlements.append(stl)
            else:
                seen_tx_settlements.add(key)
                active_settlements_by_tx_id[key] = stl

        # Create ReconciliationItems for duplicate entries
        for dup in duplicate_settlements:
            reason, action = explain_discrepancy(
                category=DiscrepancyCategory.DUPLICATE_ENTRY,
                tx_id=dup.transaction_id,
                settle_id=dup.settlement_id,
                tx_date_str=None,
                settle_date_str=dup.settlement_date.isoformat(),
                expected_amount=ZERO,
                actual_amount=dup.net_amount,
                difference=dup.net_amount,
                settle_fee=dup.fee_amount,
            )
            items.append(
                ReconciliationItem(
                    item_id=f"DUP-{dup.settlement_id}",
                    category=DiscrepancyCategory.DUPLICATE_ENTRY,
                    transaction_id=dup.transaction_id,
                    settlement_id=dup.settlement_id,
                    settlement_date=dup.settlement_date,
                    settlement_gross=dup.gross_amount,
                    settlement_fee=dup.fee_amount,
                    settlement_net=dup.net_amount,
                    expected_amount=ZERO,
                    actual_amount=dup.net_amount,
                    difference=dup.net_amount,
                    reason=reason,
                    recommended_action=action,
                    is_duplicate=True,
                    metadata={"bank_batch_id": dup.bank_batch_id},
                )
            )

        # -------------------------------------------------------------
        # Phase 3: Detect Orphan Refunds in Platform Ledger
        # -------------------------------------------------------------
        orphan_refund_ids: Set[str] = set()
        for tx in target_txs:
            if tx.type == "REFUND":
                # Check if reference_id exists in platform transactions
                if not tx.reference_id or tx.reference_id not in all_tx_by_id:
                    orphan_refund_ids.add(tx.transaction_id)
                    stl = active_settlements_by_tx_id.get(tx.transaction_id)
                    actual_net = stl.net_amount if stl else ZERO

                    reason, action = explain_discrepancy(
                        category=DiscrepancyCategory.ORPHAN_REFUND,
                        tx_id=tx.transaction_id,
                        settle_id=stl.settlement_id if stl else None,
                        tx_date_str=tx.date.isoformat(),
                        settle_date_str=stl.settlement_date.isoformat() if stl else None,
                        expected_amount=tx.net_amount,
                        actual_amount=actual_net,
                        difference=(actual_net - tx.net_amount).quantize(PENNY),
                        ref_id=tx.reference_id,
                    )

                    items.append(
                        ReconciliationItem(
                            item_id=f"ORPHAN-{tx.transaction_id}",
                            category=DiscrepancyCategory.ORPHAN_REFUND,
                            transaction_id=tx.transaction_id,
                            settlement_id=stl.settlement_id if stl else None,
                            transaction_date=tx.date,
                            settlement_date=stl.settlement_date if stl else None,
                            transaction_gross=tx.gross_amount,
                            transaction_fee=tx.fee_amount,
                            transaction_net=tx.net_amount,
                            settlement_gross=stl.gross_amount if stl else None,
                            settlement_fee=stl.fee_amount if stl else None,
                            settlement_net=stl.net_amount if stl else None,
                            expected_amount=tx.net_amount,
                            actual_amount=actual_net,
                            difference=(actual_net - tx.net_amount).quantize(PENNY),
                            reason=reason,
                            recommended_action=action,
                            metadata={"reference_id": tx.reference_id or "NONE"},
                        )
                    )

        # -------------------------------------------------------------
        # Phase 4: Match Target Period Transactions
        # -------------------------------------------------------------
        matched_settlement_keys: Set[str] = set()

        for tx in target_txs:
            if tx.transaction_id in orphan_refund_ids:
                if tx.transaction_id in active_settlements_by_tx_id:
                    matched_settlement_keys.add(tx.transaction_id)
                continue

            stl = active_settlements_by_tx_id.get(tx.transaction_id)

            if stl is None:
                # Unmatched transaction (no settlement record exists anywhere)
                reason, action = explain_discrepancy(
                    category=DiscrepancyCategory.UNMATCHED_TRANSACTION,
                    tx_id=tx.transaction_id,
                    settle_id=None,
                    tx_date_str=tx.date.isoformat(),
                    settle_date_str=None,
                    expected_amount=tx.net_amount,
                    actual_amount=ZERO,
                    difference=(-tx.net_amount).quantize(PENNY),
                )
                items.append(
                    ReconciliationItem(
                        item_id=f"UNM-TX-{tx.transaction_id}",
                        category=DiscrepancyCategory.UNMATCHED_TRANSACTION,
                        transaction_id=tx.transaction_id,
                        transaction_date=tx.date,
                        transaction_gross=tx.gross_amount,
                        transaction_fee=tx.fee_amount,
                        transaction_net=tx.net_amount,
                        expected_amount=tx.net_amount,
                        actual_amount=ZERO,
                        difference=(-tx.net_amount).quantize(PENNY),
                        reason=reason,
                        recommended_action=action,
                    )
                )
                continue

            # Settlement found! Mark settlement key as processed
            matched_settlement_keys.add(tx.transaction_id)

            # Check timing difference: did settlement date fall outside target accounting month?
            is_same_month = (
                stl.settlement_date.year == self.target_year
                and stl.settlement_date.month == self.target_month
            )

            if not is_same_month:
                # Timing difference! (e.g. November transaction settled in December)
                # Financial logic requirement: Do not classify as permanently missing payment!
                reason, action = explain_discrepancy(
                    category=DiscrepancyCategory.TIMING_DIFFERENCE,
                    tx_id=tx.transaction_id,
                    settle_id=stl.settlement_id,
                    tx_date_str=tx.date.isoformat(),
                    settle_date_str=stl.settlement_date.isoformat(),
                    expected_amount=tx.net_amount,
                    actual_amount=stl.net_amount,
                    difference=(stl.net_amount - tx.net_amount).quantize(PENNY),
                )
                items.append(
                    ReconciliationItem(
                        item_id=f"TIME-{tx.transaction_id}",
                        category=DiscrepancyCategory.TIMING_DIFFERENCE,
                        transaction_id=tx.transaction_id,
                        settlement_id=stl.settlement_id,
                        transaction_date=tx.date,
                        settlement_date=stl.settlement_date,
                        transaction_gross=tx.gross_amount,
                        transaction_fee=tx.fee_amount,
                        transaction_net=tx.net_amount,
                        settlement_gross=stl.gross_amount,
                        settlement_fee=stl.fee_amount,
                        settlement_net=stl.net_amount,
                        expected_amount=tx.net_amount,
                        actual_amount=stl.net_amount,
                        difference=(stl.net_amount - tx.net_amount).quantize(PENNY),
                        reason=reason,
                        recommended_action=action,
                        metadata={"bank_batch_id": stl.bank_batch_id},
                    )
                )
                continue

            # Same month: check amounts
            net_diff = (stl.net_amount - tx.net_amount).quantize(PENNY)
            gross_diff = (stl.gross_amount - tx.gross_amount).quantize(PENNY)

            if net_diff == ZERO and gross_diff == ZERO:
                # Perfect match!
                reason, action = explain_discrepancy(
                    category=DiscrepancyCategory.MATCHED,
                    tx_id=tx.transaction_id,
                    settle_id=stl.settlement_id,
                    tx_date_str=tx.date.isoformat(),
                    settle_date_str=stl.settlement_date.isoformat(),
                    expected_amount=tx.net_amount,
                    actual_amount=stl.net_amount,
                    difference=ZERO,
                )
                items.append(
                    ReconciliationItem(
                        item_id=f"MTC-{tx.transaction_id}",
                        category=DiscrepancyCategory.MATCHED,
                        transaction_id=tx.transaction_id,
                        settlement_id=stl.settlement_id,
                        transaction_date=tx.date,
                        settlement_date=stl.settlement_date,
                        transaction_gross=tx.gross_amount,
                        transaction_fee=tx.fee_amount,
                        transaction_net=tx.net_amount,
                        settlement_gross=stl.gross_amount,
                        settlement_fee=stl.fee_amount,
                        settlement_net=stl.net_amount,
                        expected_amount=tx.net_amount,
                        actual_amount=stl.net_amount,
                        difference=ZERO,
                        reason=reason,
                        recommended_action=action,
                        metadata={"bank_batch_id": stl.bank_batch_id},
                    )
                )
            elif gross_diff == ZERO and abs(net_diff) <= self.rounding_tolerance:
                # Rounding difference caused by per-transaction vs aggregate fee rounding!
                reason, action = explain_discrepancy(
                    category=DiscrepancyCategory.ROUNDING_DIFFERENCE,
                    tx_id=tx.transaction_id,
                    settle_id=stl.settlement_id,
                    tx_date_str=tx.date.isoformat(),
                    settle_date_str=stl.settlement_date.isoformat(),
                    expected_amount=tx.net_amount,
                    actual_amount=stl.net_amount,
                    difference=net_diff,
                    tx_gross=tx.gross_amount,
                    tx_fee=tx.fee_amount,
                    settle_fee=stl.fee_amount,
                    bank_batch_id=stl.bank_batch_id,
                )
                items.append(
                    ReconciliationItem(
                        item_id=f"RND-{tx.transaction_id}",
                        category=DiscrepancyCategory.ROUNDING_DIFFERENCE,
                        transaction_id=tx.transaction_id,
                        settlement_id=stl.settlement_id,
                        transaction_date=tx.date,
                        settlement_date=stl.settlement_date,
                        transaction_gross=tx.gross_amount,
                        transaction_fee=tx.fee_amount,
                        transaction_net=tx.net_amount,
                        settlement_gross=stl.gross_amount,
                        settlement_fee=stl.fee_amount,
                        settlement_net=stl.net_amount,
                        expected_amount=tx.net_amount,
                        actual_amount=stl.net_amount,
                        difference=net_diff,
                        reason=reason,
                        recommended_action=action,
                        metadata={"bank_batch_id": stl.bank_batch_id},
                    )
                )
            else:
                # Other amount variance
                reason = f"Amount variance on {tx.transaction_id}: Gross diff={gross_diff}, Net diff={net_diff}."
                action = "Audit acquiring fee schedule and fee deductions."
                items.append(
                    ReconciliationItem(
                        item_id=f"VAR-{tx.transaction_id}",
                        category=DiscrepancyCategory.ROUNDING_DIFFERENCE if abs(net_diff) <= Decimal("1.00") else DiscrepancyCategory.UNMATCHED_TRANSACTION,
                        transaction_id=tx.transaction_id,
                        settlement_id=stl.settlement_id,
                        transaction_date=tx.date,
                        settlement_date=stl.settlement_date,
                        transaction_gross=tx.gross_amount,
                        transaction_fee=tx.fee_amount,
                        transaction_net=tx.net_amount,
                        settlement_gross=stl.gross_amount,
                        settlement_fee=stl.fee_amount,
                        settlement_net=stl.net_amount,
                        expected_amount=tx.net_amount,
                        actual_amount=stl.net_amount,
                        difference=net_diff,
                        reason=reason,
                        recommended_action=action,
                    )
                )

        # -------------------------------------------------------------
        # Phase 5: Check for Unmatched Bank Settlements
        # -------------------------------------------------------------
        for tx_key, stl in active_settlements_by_tx_id.items():
            if tx_key not in matched_settlement_keys:
                # Settlement has no corresponding ledger transaction
                reason, action = explain_discrepancy(
                    category=DiscrepancyCategory.UNMATCHED_SETTLEMENT,
                    tx_id=stl.transaction_id,
                    settle_id=stl.settlement_id,
                    tx_date_str=None,
                    settle_date_str=stl.settlement_date.isoformat(),
                    expected_amount=ZERO,
                    actual_amount=stl.net_amount,
                    difference=stl.net_amount,
                )
                items.append(
                    ReconciliationItem(
                        item_id=f"UNM-STL-{stl.settlement_id}",
                        category=DiscrepancyCategory.UNMATCHED_SETTLEMENT,
                        transaction_id=stl.transaction_id,
                        settlement_id=stl.settlement_id,
                        settlement_date=stl.settlement_date,
                        settlement_gross=stl.gross_amount,
                        settlement_fee=stl.fee_amount,
                        settlement_net=stl.net_amount,
                        expected_amount=ZERO,
                        actual_amount=stl.net_amount,
                        difference=stl.net_amount,
                        reason=reason,
                        recommended_action=action,
                        metadata={"bank_batch_id": stl.bank_batch_id},
                    )
                )

        # -------------------------------------------------------------
        # Phase 6: Compile Financial Summaries & Category Counts
        # -------------------------------------------------------------
        # Platform totals (target period)
        platform_gross = sum((tx.gross_amount for tx in target_txs), ZERO)
        platform_fees = sum((tx.fee_amount for tx in target_txs), ZERO)
        platform_net = sum((tx.net_amount for tx in target_txs), ZERO)

        # Bank settlement totals: Strictly exclude duplicate records to avoid inflation!
        active_settlements_list = list(active_settlements_by_tx_id.values())
        bank_gross = sum((s.gross_amount for s in active_settlements_list), ZERO)
        bank_fees = sum((s.fee_amount for s in active_settlements_list), ZERO)
        bank_net = sum((s.net_amount for s in active_settlements_list), ZERO)

        # Reconciled Net (Matched items)
        reconciled_items = [it for it in items if it.category == DiscrepancyCategory.MATCHED]
        reconciled_net = sum((it.actual_amount for it in reconciled_items), ZERO)

        # Total discrepancy net (sum of differences across all non-matched items)
        non_matched_items = [it for it in items if it.category != DiscrepancyCategory.MATCHED]
        discrepancy_net = sum((abs(it.difference) for it in non_matched_items), ZERO)

        # Match rate %: Reconciled count / target transaction count
        tx_count = len(target_txs)
        match_rate = (len(reconciled_items) / tx_count * 100.0) if tx_count > 0 else 0.0

        # Counts and amounts by category
        counts_by_cat: Dict[DiscrepancyCategory, int] = {cat: 0 for cat in DiscrepancyCategory}
        amounts_by_cat: Dict[DiscrepancyCategory, Decimal] = {cat: ZERO for cat in DiscrepancyCategory}

        for it in items:
            counts_by_cat[it.category] = counts_by_cat.get(it.category, 0) + 1
            amounts_by_cat[it.category] = (amounts_by_cat.get(it.category, ZERO) + it.difference).quantize(PENNY)

        return ReconciliationSummary(
            period_label=self.period_label,
            target_year=self.target_year,
            target_month=self.target_month,
            platform_total_gross=platform_gross,
            platform_total_fees=platform_fees,
            platform_total_net=platform_net,
            platform_transaction_count=tx_count,
            bank_total_gross=bank_gross,
            bank_total_fees=bank_fees,
            bank_total_net=bank_net,
            bank_settlement_count=len(active_settlements_list),
            raw_bank_total_net_with_duplicates=raw_bank_total_net,
            reconciled_net=reconciled_net,
            discrepancy_net=discrepancy_net,
            match_rate_pct=round(match_rate, 2),
            counts_by_category=counts_by_cat,
            amounts_by_category=amounts_by_cat,
            items=items,
        )
