"""Targeted edge-case tests for reconciliation logic and duplicate defenses."""

import datetime
from decimal import Decimal

from reconai.engine.models import DiscrepancyCategory, Settlement, Transaction
from reconai.engine.reconciler import ReconciliationEngine


def test_no_next_month_writeoff():
    """Verify next-month settlement is categorized as TIMING_DIFFERENCE, never missing."""
    tx = Transaction(
        transaction_id="TX-NOV-99",
        date=datetime.date(2026, 11, 30),
        type="PAYMENT",
        status="SUCCESS",
        gross_amount=Decimal("100.00"),
        fee_amount=Decimal("3.20"),
        net_amount=Decimal("96.80"),
    )
    # Settles in December
    stl = Settlement(
        settlement_id="STL-DEC-01",
        settlement_date=datetime.date(2026, 12, 1),
        transaction_id="TX-NOV-99",
        type="CREDIT",
        gross_amount=Decimal("100.00"),
        fee_amount=Decimal("3.20"),
        net_amount=Decimal("96.80"),
    )

    engine = ReconciliationEngine([tx], [stl], target_year=2026, target_month=11)
    summary = engine.reconcile()

    assert summary.counts_by_category[DiscrepancyCategory.TIMING_DIFFERENCE] == 1
    assert summary.counts_by_category[DiscrepancyCategory.UNMATCHED_TRANSACTION] == 0
    item = summary.items[0]
    assert item.category == DiscrepancyCategory.TIMING_DIFFERENCE
    assert "in transit" in item.recommended_action.lower()


def test_triple_duplicate_prevention():
    """Verify multiple duplicates of the same settlement are all quarantined and excluded."""
    tx = Transaction(
        transaction_id="TX-100",
        date=datetime.date(2026, 11, 10),
        type="PAYMENT",
        status="SUCCESS",
        gross_amount=Decimal("200.00"),
        fee_amount=Decimal("6.10"),
        net_amount=Decimal("193.90"),
    )
    stl1 = Settlement(
        settlement_id="STL-100-A",
        settlement_date=datetime.date(2026, 11, 11),
        transaction_id="TX-100",
        type="CREDIT",
        gross_amount=Decimal("200.00"),
        fee_amount=Decimal("6.10"),
        net_amount=Decimal("193.90"),
    )
    stl2 = Settlement(
        settlement_id="STL-100-B",
        settlement_date=datetime.date(2026, 11, 11),
        transaction_id="TX-100",
        type="CREDIT",
        gross_amount=Decimal("200.00"),
        fee_amount=Decimal("6.10"),
        net_amount=Decimal("193.90"),
    )
    stl3 = Settlement(
        settlement_id="STL-100-C",
        settlement_date=datetime.date(2026, 11, 11),
        transaction_id="TX-100",
        type="CREDIT",
        gross_amount=Decimal("200.00"),
        fee_amount=Decimal("6.10"),
        net_amount=Decimal("193.90"),
    )

    engine = ReconciliationEngine([tx], [stl1, stl2, stl3], target_year=2026, target_month=11)
    summary = engine.reconcile()

    # 1 matched, 2 duplicates
    assert summary.counts_by_category[DiscrepancyCategory.MATCHED] == 1
    assert summary.counts_by_category[DiscrepancyCategory.DUPLICATE_ENTRY] == 2

    # Bank net must equal single transaction net ($193.90), NOT 3x ($581.70)!
    assert summary.bank_total_net == Decimal("193.90")
    assert summary.raw_bank_total_net_with_duplicates == Decimal("581.70")


def test_orphan_refund_without_any_reference():
    """Verify refund with None reference_id is detected as orphan refund."""
    tx = Transaction(
        transaction_id="REF-EMPTY-REF",
        date=datetime.date(2026, 11, 15),
        type="REFUND",
        status="SUCCESS",
        gross_amount=Decimal("-80.00"),
        fee_amount=Decimal("0.00"),
        net_amount=Decimal("-80.00"),
        reference_id=None,
    )
    engine = ReconciliationEngine([tx], [], target_year=2026, target_month=11)
    summary = engine.reconcile()

    assert summary.counts_by_category[DiscrepancyCategory.ORPHAN_REFUND] == 1
    item = summary.items[0]
    assert item.category == DiscrepancyCategory.ORPHAN_REFUND
