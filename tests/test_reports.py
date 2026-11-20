"""Tests for CSV and PDF report generation."""

from decimal import Decimal

from reconai.engine.reconciler import ReconciliationEngine
from reconai.reports.csv_exporter import export_reconciliation_csv
from reconai.reports.pdf_generator import generate_reconciliation_pdf


def test_export_reconciliation_csv(validated_data):
    """Verify CSV export contains header and all reconciliation line items."""
    txs, stls, _ = validated_data
    engine = ReconciliationEngine(txs, stls, 2026, 11)
    summary = engine.reconcile()

    csv_text = export_reconciliation_csv(summary)
    lines = csv_text.strip().splitlines()

    assert len(lines) == len(summary.items) + 1  # Header + rows
    assert "item_id,category,transaction_id" in lines[0]
    assert "expected_amount,actual_amount,difference" in lines[0]


def test_generate_reconciliation_pdf(validated_data):
    """Verify PDF export generates valid PDF bytes with header and content."""
    txs, stls, _ = validated_data
    engine = ReconciliationEngine(txs, stls, 2026, 11)
    summary = engine.reconcile()

    pdf_bytes = generate_reconciliation_pdf(summary)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")
