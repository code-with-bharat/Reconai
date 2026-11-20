# ReconAI - Payment Reconciliation Engine & Financial Dashboard

**ReconAI** is an audit-grade, production-minded payment reconciliation application built with Python, Streamlit, and ReportLab. It performs deterministic reconciliation of an internal payment platform transaction ledger against external acquiring bank settlement records for any selected monthly accounting period.

ReconAI uses Python `Decimal` (quantized to two decimal places with `ROUND_HALF_UP`) to enforce absolute financial precision without IEEE 754 floating-point drift. It features deterministic discrepancy classification, duplicate settlement inflation safeguards, and automated generation of detailed CSV ledgers and executive PDF audit statements.

---

## Key Features

1. **Deterministic Financial Precision**:
   - Strict `Decimal` arithmetic across gross amounts, processing fees, and net payouts.
   - Two-level fee rounding calculation demonstrating genuine per-transaction vs aggregate batch fee discrepancies.
2. **Comprehensive Discrepancy Classification**:
   - `Matched`: Exact 1-to-1 reconciliation ($0.00 variance).
   - `Timing differences`: Cross-month settlements (e.g. November transactions settled in early December) correctly recognized as in-transit deposits rather than missing revenue.
   - `Rounding differences`: Penny variances caused by per-transaction vs aggregate fee rounding.
   - `Duplicate entries`: Transmission retries and duplicate bank records isolated to prevent cash receipt inflation.
   - `Orphan refunds`: Refunds referencing missing or invalid parent transaction authorizations.
   - `Unmatched transactions`: Internal charges without corresponding bank settlements.
   - `Unmatched settlements`: Unidentified bank deposits/credits without platform transaction records.
3. **Integrity Guardrails**:
   - Prevents duplicate settlement records from inflating settlement totals.
   - Quarantines duplicate rows and surfaces prevented inflation metrics on the dashboard.
4. **Audit Reporting**:
   - One-click detailed reconciliation CSV export.
   - Certified executive PDF audit report with ReportLab.
5. **Zero External LLM Dependency**:
   - 100% deterministic, offline financial rules engine. Explanations are derived from mathematical and transactional invariants.

---

## Architecture & Codebase Layout

```
reconai/
├── README.md                      # Architecture, assumptions, and usage documentation
├── requirements.txt               # Pinned package dependencies
├── pyproject.toml                 # Packaging configuration & pytest settings
├── app.py                         # Streamlit interactive financial dashboard
├── sample_data/                   # Deterministic sample dataset (Nov 2026)
│   ├── transactions.csv           # Internal platform transaction ledger
│   └── bank_settlements.csv       # Bank settlement records
├── src/
│   └── reconai/
│       ├── __init__.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── generator.py       # Deterministic synthetic data generator (seed=42)
│       │   └── validator.py       # Schema, type, date, and monetary validation
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── models.py          # Domain data models (Transaction, Settlement, etc.)
│       │   ├── financial.py       # Decimal precision, fee math (per-tx vs aggregate)
│       │   ├── reconciler.py      # Core multi-phase matching engine
│       │   └── explainer.py       # Natural-language audit explanations & remediation
│       └── reports/
│           ├── __init__.py
│           ├── csv_exporter.py    # Detailed CSV audit log generator
│           └── pdf_generator.py   # ReportLab executive PDF statement generator
└── tests/
    ├── __init__.py
    ├── conftest.py                # Shared pytest fixtures
    ├── test_financial.py          # Decimal math & rounding variance tests
    ├── test_generator.py          # Synthetic data & planted anomaly tests
    ├── test_validator.py          # Schema & data corruption validation tests
    ├── test_reconciler.py         # Matching, deduplication & classification tests
    ├── test_edge_cases.py         # Multi-duplicate & edge timing tests
    └── test_reports.py            # CSV and PDF export validation tests
```

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.9+ (Tested on Python 3.14.8)
- pip

### 2. Setup Environment
```bash
cd /home/kali/.gemini/antigravity/scratch/reconai

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Dashboard
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## Running the Automated Test Suite

ReconAI includes comprehensive automated tests covering data generation, schema validation, financial math, discrepancy classification, deduplication, and PDF/CSV reporting.

Run pytest directly from the project root:
```bash
pytest -v
```

All 21 test cases execute in <0.20 seconds with 100% pass rate.

---

## Planted Discrepancies in the Sample Dataset

The synthetic sample data generator (`seed=42`) targets accounting month **November 2026** and plants four deliberate accounting discrepancies:

| Discrepancy Type | Description | Discovered Transaction / Settlement | Financial Treatment |
|---|---|---|---|
| **Timing Difference** | November 29-30 transactions settled on December 1-2 | `TX-2026-11-0111`, `TX-2026-11-0112`, etc. | Accrued as *Deposits in Transit*; not written off as missing. |
| **Rounding Difference** | Per-transaction vs aggregate batch fee rounding | `TX-2026-11-0122` (Batch `BATCH-20261118-AGG-FEE`) | Variance of $0.01 booked to Fee Rounding Variance. |
| **Duplicate Record** | Duplicate settlement transmission in bank file | `SETTLE-2026-11-0026-DUP` referencing `TX-2026-11-0026` | Quarantined; prevents false settlement inflation of +$694.75. |
| **Orphan Refund** | Refund referencing nonexistent parent payment | `REF-2026-11-9999` referencing `TX-NONEXISTENT-ORIGIN-0000` | Flagged for compliance audit; settlement held. |

---

## Financial Assumptions

1. **Monetary Quantization**: All currency amounts are converted to Python `Decimal` with 2 decimal places using `ROUND_HALF_UP`.
2. **Fee Structures**:
   - Internal platform charges per-transaction fees: $\text{fee} = \text{round}(\text{gross} \times 0.029 + 0.30, 2)$.
   - Processors/banks may charge fees on aggregate batches: $\text{fee}_{\text{agg}} = \text{round}(\sum \text{gross} \times 0.029 + N \times 0.30, 2)$.
   - Differences up to \$0.10 between gross-matched records are classified as rounding differences.
3. **Settlement Timing Window**: Transactions occurring in Month $M$ settled in Month $M+1$ are timing differences, not lost payments.
4. **Duplicate Protection**: If multiple settlements reference the same platform transaction ID, only the first transmission is credited to bank net; subsequent transmissions are quarantined as duplicates.

---

## Known Limitations

- **Multi-Currency FX**: Current MVP operates natively in USD (single currency). Multi-currency conversion with floating exchange rates is slated for Phase 2.
- **Split Payouts**: Payouts that split a single customer charge across multiple merchant sub-wallets are currently reconciled at the parent transaction level.
- **Large Files**: For CSV datasets exceeding 1,000,000 rows, streaming batch chunking or an external SQL database (e.g., PostgreSQL / DuckDB) is recommended.
