"""Tests for the core reconciliation engine and discrepancy classification."""

from decimal import Decimal

from reconai.engine.models import DiscrepancyCategory
from reconai.engine.reconciler import ReconciliationEngine


def test_reconcile_full_sample_dataset(validated_data):
    """Verify reconciliation on sample data finds all expected categories."""
    txs, stls, meta = validated_data
    engine = ReconciliationEngine(txs, stls, target_year=2026, target_month=11)
    summary = engine.reconcile()

    # 1. Match rate and period
    assert summary.period_label == "2026-11"
    assert summary.platform_transaction_count > 0
    assert summary.match_rate_pct > 80.0

    # 2. Timing differences: November txs settled in December
    timing_items = [it for it in summary.items if it.category == DiscrepancyCategory.TIMING_DIFFERENCE]
    assert len(timing_items) == len(meta["timing_difference_tx_ids"])
    for it in timing_items:
        assert it.transaction_id in meta["timing_difference_tx_ids"]
        assert it.transaction_date.month == 11
        assert it.settlement_date.month == 12

    # 3. Rounding differences: fee difference caused by per-tx vs aggregate fee rounding
    rnd_items = [it for it in summary.items if it.category == DiscrepancyCategory.ROUNDING_DIFFERENCE]
    assert len(rnd_items) >= 1
    target_rnd = next(it for it in rnd_items if it.transaction_id == meta["rounding_difference_tx_id"])
    assert target_rnd.transaction_gross == target_rnd.settlement_gross
    assert target_rnd.difference != Decimal("0.00")
    assert "rounding" in target_rnd.reason.lower()

    # 4. Duplicate entries: duplicate settlement isolated and does NOT inflate bank totals
    dup_items = [it for it in summary.items if it.category == DiscrepancyCategory.DUPLICATE_ENTRY]
    assert len(dup_items) == 1
    assert dup_items[0].transaction_id == meta["duplicate_tx_id"]
    assert dup_items[0].is_duplicate is True

    # Critical requirement: Prevent duplicate records from inflating settlement totals
    assert summary.bank_total_net < summary.raw_bank_total_net_with_duplicates
    prevented_inflation = summary.raw_bank_total_net_with_duplicates - summary.bank_total_net
    assert prevented_inflation == dup_items[0].actual_amount

    # 5. Orphan refunds: referencing nonexistent original transaction
    orphan_items = [it for it in summary.items if it.category == DiscrepancyCategory.ORPHAN_REFUND]
    assert len(orphan_items) == 1
    assert orphan_items[0].transaction_id == meta["orphan_refund_tx_id"]
    assert "orphan" in orphan_items[0].reason.lower()

    # 6. Unmatched transactions and settlements
    unm_tx_items = [it for it in summary.items if it.category == DiscrepancyCategory.UNMATCHED_TRANSACTION]
    unm_stl_items = [it for it in summary.items if it.category == DiscrepancyCategory.UNMATCHED_SETTLEMENT]
    assert len(unm_tx_items) >= 1
    assert len(unm_stl_items) >= 1


def test_reconciliation_zero_variance_on_exact_match(validated_data):
    """Verify that perfectly matching items have exact zero variance and Matched category."""
    txs, stls, _ = validated_data
    engine = ReconciliationEngine(txs, stls, target_year=2026, target_month=11)
    summary = engine.reconcile()

    matched_items = [it for it in summary.items if it.category == DiscrepancyCategory.MATCHED]
    assert len(matched_items) > 100
    for it in matched_items:
        assert it.difference == Decimal("0.00")
        assert it.expected_amount == it.actual_amount
