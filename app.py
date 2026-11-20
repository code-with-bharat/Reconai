"""ReconAI - Payment Reconciliation Application Streamlit Dashboard."""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import sys
import pandas as pd
import streamlit as st

# Add src to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from reconai.data.generator import generate_synthetic_data, save_synthetic_data_csv
from reconai.data.validator import validate_settlements, validate_transactions
from reconai.engine.financial import format_currency, to_decimal
from reconai.engine.models import DiscrepancyCategory, ReconciliationSummary
from reconai.engine.reconciler import ReconciliationEngine
from reconai.reports.csv_exporter import export_reconciliation_csv
from reconai.reports.pdf_generator import generate_reconciliation_pdf


st.set_page_config(
    page_title="ReconAI | Payment Reconciliation & Audit",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for clean executive styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0F172A;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 4px;
    }
    .badge-matched { background-color: #DCFCE7; color: #166534; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-timing { background-color: #DBEAFE; color: #1E40AF; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-rounding { background-color: #FEF9C3; color: #854D0E; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-duplicate { background-color: #FEE2E2; color: #991B1B; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-orphan { background-color: #F3E8FF; color: #6B21A8; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    .badge-unmatched { background-color: #FFEDD5; color: #9A3412; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


SAMPLE_DATA_DIR = Path(__file__).resolve().parent / "sample_data"


def ensure_sample_data():
    """Ensure sample CSV files exist."""
    tx_file = SAMPLE_DATA_DIR / "transactions.csv"
    stl_file = SAMPLE_DATA_DIR / "bank_settlements.csv"
    if not tx_file.exists() or not stl_file.exists():
        txs, stls, _ = generate_synthetic_data(seed=42)
        save_synthetic_data_csv(txs, stls, SAMPLE_DATA_DIR)


ensure_sample_data()

# -------------------------------------------------------------
# Sidebar Configuration
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚖️ ReconAI")
    st.markdown("*Payment Reconciliation & Audit System*")
    st.divider()

    st.subheader("Data Source")
    data_source = st.radio(
        "Select Dataset Mode:",
        ["Pre-Generated Sample Dataset", "Upload Custom CSVs"],
        index=0,
    )

    df_transactions: pd.DataFrame | None = None
    df_settlements: pd.DataFrame | None = None

    if data_source == "Pre-Generated Sample Dataset":
        st.info("Using planted sample dataset (Nov 2026) with all 4 target discrepancies.")
        if st.button("Regenerate Sample Data (Seed 42)"):
            txs, stls, meta = generate_synthetic_data(seed=42)
            save_synthetic_data_csv(txs, stls, SAMPLE_DATA_DIR)
            st.success("Fresh sample dataset generated!")

        df_transactions = pd.read_csv(SAMPLE_DATA_DIR / "transactions.csv")
        df_settlements = pd.read_csv(SAMPLE_DATA_DIR / "bank_settlements.csv")

    else:
        st.subheader("Upload CSV Files")
        tx_upload = st.file_uploader("Internal Transactions CSV", type=["csv"], key="tx_file")
        stl_upload = st.file_uploader("Bank Settlements CSV", type=["csv"], key="stl_file")

        if tx_upload is not None:
            df_transactions = pd.read_csv(tx_upload)
        if stl_upload is not None:
            df_settlements = pd.read_csv(stl_upload)

    st.divider()
    st.subheader("Reconciliation Scope")
    target_year = st.number_input("Accounting Year", min_value=2020, max_value=2030, value=2026, step=1)
    target_month = st.number_input("Accounting Month", min_value=1, max_value=12, value=11, step=1)
    rounding_tol = st.number_input("Rounding Tolerance ($)", min_value=0.01, max_value=1.00, value=0.10, step=0.01)

    st.divider()
    st.caption("Engine: Python Decimal (IEEE 854)")
    st.caption("LLM API requirement: None (100% Deterministic)")


# -------------------------------------------------------------
# Main Application Flow
# -------------------------------------------------------------
st.markdown('<div class="main-header">ReconAI - Payment Reconciliation Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Automated financial ledger vs bank settlement reconciliation with Python Decimal precision</div>',
    unsafe_allow_html=True,
)

if df_transactions is None or df_settlements is None:
    st.warning("Please provide both the Transactions Ledger and Bank Settlements files to initiate reconciliation.")
    st.stop()

# Validate datasets
val_tx = validate_transactions(df_transactions)
val_stl = validate_settlements(df_settlements)

if not val_tx.is_valid:
    st.error(f"Transactions file validation failed: {val_tx.errors}")
    st.stop()

if not val_stl.is_valid:
    st.error(f"Settlements file validation failed: {val_stl.errors}")
    st.stop()

# Run reconciliation
engine = ReconciliationEngine(
    transactions=val_tx.parsed_transactions,
    settlements=val_stl.parsed_settlements,
    target_year=int(target_year),
    target_month=int(target_month),
    rounding_tolerance=Decimal(str(rounding_tol)),
)
summary = engine.reconcile()


# Tabs layout
tab_overview, tab_results, tab_investigation, tab_explorer, tab_export = st.tabs([
    "📊 Overview",
    "📑 Reconciliation Results",
    "🔍 Discrepancy Investigation",
    "📁 Data Explorer",
    "📥 Report Export",
])

# -------------------------------------------------------------
# TAB 1: OVERVIEW
# -------------------------------------------------------------
with tab_overview:
    st.markdown(f"#### Reconciliation Period: **{summary.period_label}**")

    # High-level KPI Row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Platform Ledger (Net)</div>
                <div class="metric-value">{format_currency(summary.platform_total_net)}</div>
                <div class="metric-sub">Gross: {format_currency(summary.platform_total_gross)} | Fees: {format_currency(summary.platform_total_fees)}<br>{summary.platform_transaction_count} transactions</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Bank Settled (Net)</div>
                <div class="metric-value">{format_currency(summary.bank_total_net)}</div>
                <div class="metric-sub">Gross: {format_currency(summary.bank_total_gross)} | Fees: {format_currency(summary.bank_total_fees)}<br>{summary.bank_settlement_count} settlements (de-duplicated)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Reconciled Net (Matched)</div>
                <div class="metric-value" style="color: #16A34A;">{format_currency(summary.reconciled_net)}</div>
                <div class="metric-sub">Match Rate: <b>{summary.match_rate_pct:.1f}%</b><br>{summary.counts_by_category[DiscrepancyCategory.MATCHED]} verified matched records</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col4:
        total_issues = sum(
            count for cat, count in summary.counts_by_category.items()
            if cat != DiscrepancyCategory.MATCHED
        )
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Discrepancies & Variances</div>
                <div class="metric-value" style="color: #DC2626;">{format_currency(summary.discrepancy_net)}</div>
                <div class="metric-sub">{total_issues} flagged item(s)<br>Requiring audit review or adjustment</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # Fraud & Duplicate Prevention Callout Banner
    prevented_inflation = summary.raw_bank_total_net_with_duplicates - summary.bank_total_net
    if summary.counts_by_category[DiscrepancyCategory.DUPLICATE_ENTRY] > 0:
        st.success(
            f"🛡️ **Integrity Control Active**: ReconAI detected "
            f"**{summary.counts_by_category[DiscrepancyCategory.DUPLICATE_ENTRY]} duplicate bank settlement record(s)**. "
            f"These duplicates were quarantined and excluded from bank totals, successfully preventing "
            f"**+{format_currency(prevented_inflation)}** of false settlement inflation."
        )

    st.divider()

    # Visual Breakdown Section
    st.subheader("Discrepancy & Reconciliation Breakdown")
    ch_col1, ch_col2 = st.columns(2)

    cat_counts_df = pd.DataFrame([
        {"Category": cat.value, "Count": count, "Amount": float(summary.amounts_by_category[cat])}
        for cat, count in summary.counts_by_category.items()
    ])

    with ch_col1:
        st.markdown("**Record Counts by Classification**")
        st.bar_chart(cat_counts_df.set_index("Category")["Count"], height=280)

    with ch_col2:
        st.markdown("**Net Discrepancy Variance Amounts ($)**")
        st.bar_chart(cat_counts_df.set_index("Category")["Amount"], height=280)

    st.divider()
    st.subheader("Summary Table by Category")
    summary_table_data = []
    for cat in DiscrepancyCategory:
        cnt = summary.counts_by_category[cat]
        amt = summary.amounts_by_category[cat]
        summary_table_data.append({
            "Classification Category": cat.value,
            "Record Count": cnt,
            "Net Difference": format_currency(amt),
            "Status / Action": "Fully Reconciled" if cat == DiscrepancyCategory.MATCHED else "Investigation / Accrual Required",
        })
    st.dataframe(pd.DataFrame(summary_table_data), use_container_width=True, hide_index=True)


# -------------------------------------------------------------
# TAB 2: RECONCILIATION RESULTS
# -------------------------------------------------------------
with tab_results:
    st.subheader("Itemized Reconciliation Ledger")

    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 2])
    with filter_col1:
        selected_category = st.selectbox(
            "Filter by Category:",
            ["All"] + [c.value for c in DiscrepancyCategory],
            index=0,
        )
    with filter_col2:
        search_kw = st.text_input("Search (Transaction ID / Settlement ID):", "")
    with filter_col3:
        only_discrepancies = st.checkbox("Show only discrepancies (exclude Matched)", value=False)

    # Build items dataframe
    table_rows = []
    for it in summary.items:
        if only_discrepancies and it.category == DiscrepancyCategory.MATCHED:
            continue
        if selected_category != "All" and it.category.value != selected_category:
            continue
        if search_kw:
            kw = search_kw.lower()
            tx_match = it.transaction_id and kw in it.transaction_id.lower()
            stl_match = it.settlement_id and kw in it.settlement_id.lower()
            if not (tx_match or stl_match):
                continue

        table_rows.append({
            "Item ID": it.item_id,
            "Category": it.category.value,
            "Transaction ID": it.transaction_id or "—",
            "Settlement ID": it.settlement_id or "—",
            "Tx Date": it.transaction_date.isoformat() if it.transaction_date else "—",
            "Settle Date": it.settlement_date.isoformat() if it.settlement_date else "—",
            "Expected ($)": format_currency(it.expected_amount),
            "Actual ($)": format_currency(it.actual_amount),
            "Difference ($)": format_currency(it.difference),
            "Reason": it.reason,
            "Recommended Action": it.recommended_action,
        })

    results_df = pd.DataFrame(table_rows)
    st.write(f"Displaying **{len(results_df)}** records matching filter criteria.")
    st.dataframe(
        results_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Reason": st.column_config.TextColumn(width="large"),
            "Recommended Action": st.column_config.TextColumn(width="medium"),
        },
    )

    # Detailed Item Inspector Expander
    st.divider()
    st.subheader("🔍 Deep-Dive Item Inspector")
    item_ids = [it.item_id for it in summary.items]
    selected_item_id = st.selectbox("Select Item ID to Inspect Full Metadata:", item_ids)

    if selected_item_id:
        selected_item = next((it for it in summary.items if it.item_id == selected_item_id), None)
        if selected_item:
            st.markdown(f"**Classification:** `{selected_item.category.value}`")
            ins_col1, ins_col2 = st.columns(2)
            with ins_col1:
                st.markdown("##### Platform Transaction Ledger Record")
                st.write(f"- **Transaction ID:** `{selected_item.transaction_id or 'N/A'}`")
                st.write(f"- **Transaction Date:** {selected_item.transaction_date or 'N/A'}")
                st.write(f"- **Gross Amount:** {format_currency(selected_item.transaction_gross)}")
                st.write(f"- **Fee Amount:** {format_currency(selected_item.transaction_fee)}")
                st.write(f"- **Net Amount (Expected):** {format_currency(selected_item.transaction_net)}")
            with ins_col2:
                st.markdown("##### Bank Settlement Statement Record")
                st.write(f"- **Settlement ID:** `{selected_item.settlement_id or 'N/A'}`")
                st.write(f"- **Settlement Date:** {selected_item.settlement_date or 'N/A'}")
                st.write(f"- **Gross Amount:** {format_currency(selected_item.settlement_gross)}")
                st.write(f"- **Fee Amount:** {format_currency(selected_item.settlement_fee)}")
                st.write(f"- **Net Amount (Actual):** {format_currency(selected_item.settlement_net)}")

            st.info(f"**Audit Explanation:** {selected_item.reason}")
            st.warning(f"**Accounting Remediation:** {selected_item.recommended_action}")


# -------------------------------------------------------------
# TAB 3: DISCREPANCY INVESTIGATION
# -------------------------------------------------------------
with tab_investigation:
    st.subheader("Discrepancy Investigation & Root-Cause Analysis")
    st.markdown(
        "Drill down into each of the planted accounting anomalies discovered by the reconciliation engine."
    )

    # 1. Timing Differences
    with st.expander("⏱️ 1. Timing Differences (Cross-Month Settlements)", expanded=True):
        st.markdown(
            """
            **Financial Root Cause:**
            Late-month transactions processed on November 29-30 cleared at the acquiring bank on December 1-2.
            In accordance with accrual accounting principles, **these must not be written off as permanently missing payments**.
            Instead, they are classified as *Deposits / Settlements in Transit*.
            """
        )
        timing_items = [it for it in summary.items if it.category == DiscrepancyCategory.TIMING_DIFFERENCE]
        if timing_items:
            t_data = [{
                "Tx ID": it.transaction_id,
                "Tx Date (Ledger)": str(it.transaction_date),
                "Settlement Date (Bank)": str(it.settlement_date),
                "Expected Net": format_currency(it.expected_amount),
                "Actual Net": format_currency(it.actual_amount),
                "Difference": format_currency(it.difference),
                "Action": it.recommended_action,
            } for it in timing_items]
            st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)
        else:
            st.write("No timing differences found.")

    # 2. Rounding Differences
    with st.expander("🔢 2. Rounding Differences (Per-Transaction vs Aggregate Fee Rounding)", expanded=True):
        st.markdown(
            """
            **Financial Root Cause:**
            A rounding variance arises when the internal platform calculates processing fees per-transaction
            (`round(gross * rate + fixed, 2)`), while the bank or payment processor deducts fees on the aggregate batch
            (`round(sum(gross) * rate + N * fixed, 2)`). The mathematical accumulation of half-cents produces a penny variance.
            """
        )
        rnd_items = [it for it in summary.items if it.category == DiscrepancyCategory.ROUNDING_DIFFERENCE]
        if rnd_items:
            r_data = [{
                "Tx ID": it.transaction_id,
                "Gross Amount": format_currency(it.transaction_gross),
                "Platform Fee": format_currency(it.transaction_fee),
                "Bank Fee": format_currency(it.settlement_fee),
                "Platform Net": format_currency(it.expected_amount),
                "Bank Net": format_currency(it.actual_amount),
                "Rounding Variance": format_currency(it.difference),
                "Audit Explanation": it.reason,
            } for it in rnd_items]
            st.dataframe(pd.DataFrame(r_data), use_container_width=True, hide_index=True)
        else:
            st.write("No rounding differences found.")

    # 3. Duplicate Records
    with st.expander("♊ 3. Duplicate Records (Settlement Total Inflation Prevention)", expanded=True):
        st.markdown(
            """
            **Financial Root Cause & Guardrail:**
            A duplicate transmission in the bank settlements file would artificially inflate reported cash receipts.
            ReconAI's deduplication quarantine isolates duplicate lines, ensuring the bank total matches true economic settlement.
            """
        )
        dup_items = [it for it in summary.items if it.category == DiscrepancyCategory.DUPLICATE_ENTRY]
        if dup_items:
            d_data = [{
                "Settlement ID": it.settlement_id,
                "Referenced Tx ID": it.transaction_id,
                "Duplicate Amount": format_currency(it.actual_amount),
                "Status": "QUARANTINED (Excluded from Bank Totals)",
                "Action": it.recommended_action,
            } for it in dup_items]
            st.dataframe(pd.DataFrame(d_data), use_container_width=True, hide_index=True)
        else:
            st.write("No duplicate entries found.")

    # 4. Orphan Refunds
    with st.expander("⚠️ 4. Orphan Refunds (Nonexistent Original Transaction Reference)", expanded=True):
        st.markdown(
            """
            **Financial Root Cause:**
            A refund transaction references a parent transaction ID that does not exist in the ledger.
            This could indicate manual operator error, legacy migration data mismatch, or unauthorized payout injection.
            """
        )
        orphan_items = [it for it in summary.items if it.category == DiscrepancyCategory.ORPHAN_REFUND]
        if orphan_items:
            o_data = [{
                "Refund Tx ID": it.transaction_id,
                "Refund Date": str(it.transaction_date),
                "Referenced Parent ID": it.metadata.get("reference_id", "MISSING"),
                "Refund Amount": format_currency(it.expected_amount),
                "Status": "FLAGGED FOR COMPLIANCE REVIEW",
                "Action": it.recommended_action,
            } for it in orphan_items]
            st.dataframe(pd.DataFrame(o_data), use_container_width=True, hide_index=True)
        else:
            st.write("No orphan refunds found.")

    # 5. Unmatched Transactions & Settlements
    with st.expander("❓ 5. Unmatched Transactions & Settlements", expanded=False):
        unm_tx_items = [it for it in summary.items if it.category == DiscrepancyCategory.UNMATCHED_TRANSACTION]
        unm_stl_items = [it for it in summary.items if it.category == DiscrepancyCategory.UNMATCHED_SETTLEMENT]

        st.markdown("##### Unmatched Platform Transactions (Missing Bank Settlement)")
        if unm_tx_items:
            st.dataframe(pd.DataFrame([{
                "Tx ID": it.transaction_id,
                "Tx Date": str(it.transaction_date),
                "Expected Net": format_currency(it.expected_amount),
                "Reason": it.reason,
            } for it in unm_tx_items]), use_container_width=True, hide_index=True)

        st.markdown("##### Unmatched Bank Settlements (Missing Platform Ledger Record)")
        if unm_stl_items:
            st.dataframe(pd.DataFrame([{
                "Settlement ID": it.settlement_id,
                "Settlement Date": str(it.settlement_date),
                "Actual Net": format_currency(it.actual_amount),
                "Reason": it.reason,
            } for it in unm_stl_items]), use_container_width=True, hide_index=True)


# -------------------------------------------------------------
# TAB 4: DATA EXPLORER
# -------------------------------------------------------------
with tab_explorer:
    st.subheader("Raw Data Explorer & Schema Audit")

    explorer_view = st.radio("Select View:", ["Platform Transactions Ledger", "Bank Settlements Statement"], horizontal=True)

    if explorer_view == "Platform Transactions Ledger":
        st.markdown(f"**Loaded {len(df_transactions)} transaction records.** Schema status: `VALID` ✅")
        st.dataframe(df_transactions, use_container_width=True)
    else:
        st.markdown(f"**Loaded {len(df_settlements)} bank settlement records.** Schema status: `VALID` ✅")
        st.dataframe(df_settlements, use_container_width=True)


# -------------------------------------------------------------
# TAB 5: REPORT EXPORT
# -------------------------------------------------------------
with tab_export:
    st.subheader("Export Audit & Reconciliation Reports")
    st.markdown(
        "Download certified reconciliation statements and detailed discrepancy audit files."
    )

    # Generate CSV and PDF in memory
    csv_data = export_reconciliation_csv(summary)
    pdf_bytes = generate_reconciliation_pdf(summary)

    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        st.markdown("### 📑 Detailed Reconciliation CSV")
        st.markdown(
            "Export complete line-item reconciliation results containing all transaction IDs, settlement IDs, "
            "monetary fields, fee breakdowns, classifications, and explanations."
        )
        st.download_button(
            label="⬇️ Download Detailed Results (CSV)",
            data=csv_data,
            file_name=f"reconai_results_{summary.period_label}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with exp_col2:
        st.markdown("### 📄 Certified Summary PDF Report")
        st.markdown(
            "Export an executive audit report formatted for financial controllers and internal auditors. "
            "Includes key KPI metrics, duplicate prevention disclosures, and discrepancy breakdown."
        )
        st.download_button(
            label="⬇️ Download Summary Report (PDF)",
            data=pdf_bytes,
            file_name=f"reconai_summary_report_{summary.period_label}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.divider()
    st.markdown("### 💾 Export Raw Synthetic Datasets")
    raw_col1, raw_col2 = st.columns(2)
    with raw_col1:
        with open(SAMPLE_DATA_DIR / "transactions.csv", "r", encoding="utf-8") as f:
            st.download_button(
                "⬇️ Download transactions.csv",
                f.read(),
                file_name="transactions.csv",
                mime="text/csv",
            )
    with raw_col2:
        with open(SAMPLE_DATA_DIR / "bank_settlements.csv", "r", encoding="utf-8") as f:
            st.download_button(
                "⬇️ Download bank_settlements.csv",
                f.read(),
                file_name="bank_settlements.csv",
                mime="text/csv",
            )
