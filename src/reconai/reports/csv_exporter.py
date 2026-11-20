"""CSV Export generation for detailed reconciliation results."""

from __future__ import annotations

import csv
import io
from typing import List

from reconai.engine.models import ReconciliationItem, ReconciliationSummary


def export_reconciliation_csv(summary: ReconciliationSummary) -> str:
    """Generate detailed audit-ready CSV text from reconciliation summary items."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "item_id",
        "category",
        "transaction_id",
        "settlement_id",
        "transaction_date",
        "settlement_date",
        "expected_amount",
        "actual_amount",
        "difference",
        "transaction_gross",
        "transaction_fee",
        "transaction_net",
        "settlement_gross",
        "settlement_fee",
        "settlement_net",
        "is_duplicate",
        "reason",
        "recommended_action",
    ])

    for it in summary.items:
        writer.writerow([
            it.item_id,
            it.category.value,
            it.transaction_id or "",
            it.settlement_id or "",
            it.transaction_date.isoformat() if it.transaction_date else "",
            it.settlement_date.isoformat() if it.settlement_date else "",
            f"{it.expected_amount:.2f}",
            f"{it.actual_amount:.2f}",
            f"{it.difference:.2f}",
            f"{it.transaction_gross:.2f}" if it.transaction_gross is not None else "",
            f"{it.transaction_fee:.2f}" if it.transaction_fee is not None else "",
            f"{it.transaction_net:.2f}" if it.transaction_net is not None else "",
            f"{it.settlement_gross:.2f}" if it.settlement_gross is not None else "",
            f"{it.settlement_fee:.2f}" if it.settlement_fee is not None else "",
            f"{it.settlement_net:.2f}" if it.settlement_net is not None else "",
            "TRUE" if it.is_duplicate else "FALSE",
            it.reason,
            it.recommended_action,
        ])

    return output.getvalue()
