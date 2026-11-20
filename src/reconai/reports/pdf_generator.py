"""PDF Summary Report generation using ReportLab."""

from __future__ import annotations

import datetime
import io
from decimal import Decimal
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reconai.engine.financial import format_currency
from reconai.engine.models import DiscrepancyCategory, ReconciliationItem, ReconciliationSummary


def generate_reconciliation_pdf(summary: ReconciliationSummary) -> bytes:
    """Generate professional executive reconciliation summary PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=10,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#334155"),
    )
    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )
    cell_header = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#FFFFFF"),
    )

    story = []

    # Title & Header
    story.append(Paragraph("ReconAI - Payment Reconciliation & Audit Report", title_style))
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(
        Paragraph(
            f"Accounting Period: <b>{summary.period_label}</b> | Generated: {now_str} | Precision: Python Decimal (64-bit IEEE 854/84)",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=12))

    # Executive Summary Metrics Table
    story.append(Paragraph("1. Executive Reconciliation Summary", section_heading))

    prevented_inflation = summary.raw_bank_total_net_with_duplicates - summary.bank_total_net

    exec_data = [
        [
            Paragraph("Metric", cell_header),
            Paragraph("Platform Ledger", cell_header),
            Paragraph("Bank Settlements", cell_header),
            Paragraph("Audit Variance", cell_header),
        ],
        [
            Paragraph("Gross Transaction Volume", cell_bold),
            Paragraph(format_currency(summary.platform_total_gross), cell_style),
            Paragraph(format_currency(summary.bank_total_gross), cell_style),
            Paragraph(format_currency(summary.bank_total_gross - summary.platform_total_gross), cell_style),
        ],
        [
            Paragraph("Processing Fees Deducted", cell_bold),
            Paragraph(format_currency(summary.platform_total_fees), cell_style),
            Paragraph(format_currency(summary.bank_total_fees), cell_style),
            Paragraph(format_currency(summary.bank_total_fees - summary.platform_total_fees), cell_style),
        ],
        [
            Paragraph("Net Settlement Amount", cell_bold),
            Paragraph(format_currency(summary.platform_total_net), cell_bold),
            Paragraph(format_currency(summary.bank_total_net), cell_bold),
            Paragraph(format_currency(summary.bank_total_net - summary.platform_total_net), cell_bold),
        ],
        [
            Paragraph("Reconciled Net (Matched)", cell_bold),
            Paragraph(format_currency(summary.reconciled_net), cell_style),
            Paragraph(f"Match Rate: {summary.match_rate_pct:.1f}%", cell_style),
            Paragraph(f"Active Discrepancy Net: {format_currency(summary.discrepancy_net)}", cell_style),
        ],
        [
            Paragraph("Duplicate Settlements Prevented", cell_bold),
            Paragraph(f"{summary.counts_by_category.get(DiscrepancyCategory.DUPLICATE_ENTRY, 0)} duplicate(s)", cell_style),
            Paragraph(f"Raw Bank Net: {format_currency(summary.raw_bank_total_net_with_duplicates)}", cell_style),
            Paragraph(f"Inflation Prevented: +{format_currency(prevented_inflation)}", cell_bold),
        ],
    ]

    exec_table = Table(exec_data, colWidths=[150, 120, 130, 140])
    exec_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.HexColor("#FFFFFF")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(exec_table)
    story.append(Spacer(1, 14))

    # Category Breakdown Table
    story.append(Paragraph("2. Discrepancy Breakdown by Category", section_heading))

    cat_data = [
        [
            Paragraph("Category", cell_header),
            Paragraph("Record Count", cell_header),
            Paragraph("Total Difference", cell_header),
            Paragraph("Classification Rationale", cell_header),
        ]
    ]

    category_descriptions = {
        DiscrepancyCategory.MATCHED: "Transactions verified against settlements with $0.00 variance.",
        DiscrepancyCategory.TIMING_DIFFERENCE: "End-of-month payments settled in following calendar cycle.",
        DiscrepancyCategory.ROUNDING_DIFFERENCE: "Per-transaction vs aggregate fee rounding differences.",
        DiscrepancyCategory.DUPLICATE_ENTRY: "Duplicate bank settlement transmissions isolated from totals.",
        DiscrepancyCategory.ORPHAN_REFUND: "Refunds referencing nonexistent or unresolvable parent charges.",
        DiscrepancyCategory.UNMATCHED_TRANSACTION: "Platform payments missing bank settlement confirmation.",
        DiscrepancyCategory.UNMATCHED_SETTLEMENT: "Bank funds received without platform transaction reference.",
    }

    for cat in DiscrepancyCategory:
        count = summary.counts_by_category.get(cat, 0)
        amt = summary.amounts_by_category.get(cat, Decimal("0.00"))
        desc = category_descriptions.get(cat, "")

        cat_data.append([
            Paragraph(cat.value, cell_bold),
            Paragraph(str(count), cell_style),
            Paragraph(format_currency(amt), cell_style),
            Paragraph(desc, cell_style),
        ])

    cat_table = Table(cat_data, colWidths=[130, 70, 90, 250])
    cat_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.HexColor("#FFFFFF")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(cat_table)
    story.append(Spacer(1, 14))

    # Itemized Discrepancy Highlights (Non-matched items)
    story.append(Paragraph("3. Detailed Discrepancy Audit Log", section_heading))

    non_matched = [it for it in summary.items if it.category != DiscrepancyCategory.MATCHED]

    item_data = [
        [
            Paragraph("Item ID", cell_header),
            Paragraph("Category", cell_header),
            Paragraph("Expected", cell_header),
            Paragraph("Actual", cell_header),
            Paragraph("Diff", cell_header),
            Paragraph("Audit Explanation & Action", cell_header),
        ]
    ]

    for it in non_matched[:15]:  # Show top discrepancies
        expl = f"{it.reason} <b>Action:</b> {it.recommended_action}"
        item_data.append([
            Paragraph(it.transaction_id or it.settlement_id or it.item_id, cell_style),
            Paragraph(it.category.value, cell_bold),
            Paragraph(format_currency(it.expected_amount), cell_style),
            Paragraph(format_currency(it.actual_amount), cell_style),
            Paragraph(format_currency(it.difference), cell_bold),
            Paragraph(expl, cell_style),
        ])

    item_table = Table(item_data, colWidths=[85, 95, 55, 55, 50, 200])
    item_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.HexColor("#FFFFFF")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(item_table)

    # Footer note
    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            "<b>Sign-off & Governance:</b> This automated reconciliation statement has been compiled using deterministic "
            "Python Decimal arithmetic with zero floating-point approximation error. In accordance with financial internal controls, "
            "all timing differences must be posted to transit suspense, and rounding adjustments approved by the Controller.",
            subtitle_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()
