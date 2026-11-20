"""Validation layer for transaction ledgers and bank settlements."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from reconai.engine.financial import to_decimal
from reconai.engine.models import Transaction, Settlement


REQUIRED_TRANSACTION_COLS = {
    "transaction_id",
    "date",
    "type",
    "status",
    "gross_amount",
    "fee_amount",
    "net_amount",
}

REQUIRED_SETTLEMENT_COLS = {
    "settlement_id",
    "settlement_date",
    "transaction_id",
    "type",
    "gross_amount",
    "fee_amount",
    "net_amount",
}

VALID_TX_TYPES = {"PAYMENT", "REFUND"}
VALID_TX_STATUSES = {"SUCCESS", "FAILED", "PENDING"}
VALID_SETTLEMENT_TYPES = {"CREDIT", "DEBIT"}


@dataclass
class ValidationReport:
    """Detailed validation outcomes for a dataset."""
    dataset_name: str
    is_valid: bool
    total_rows: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    parsed_transactions: List[Transaction] = field(default_factory=list)
    parsed_settlements: List[Settlement] = field(default_factory=list)


def parse_date(val: Any) -> datetime.date:
    """Parse date safely from string, date, or timestamp."""
    if isinstance(val, datetime.date) and not isinstance(val, datetime.datetime):
        return val
    if isinstance(val, (datetime.datetime, pd.Timestamp)):
        return val.date()

    date_str = str(val).strip()
    # Try common formats
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: '{val}'. Expected YYYY-MM-DD.")


def validate_transactions(df: pd.DataFrame) -> ValidationReport:
    """Validate internal platform transaction ledger DataFrame."""
    report = ValidationReport(dataset_name="Transactions Ledger", is_valid=True, total_rows=len(df))

    # 1. Check required columns
    missing_cols = REQUIRED_TRANSACTION_COLS - set(df.columns)
    if missing_cols:
        report.is_valid = False
        report.errors.append(f"Missing required columns: {sorted(list(missing_cols))}")
        return report

    parsed: List[Transaction] = []

    for idx, row in df.iterrows():
        row_num = idx + 1
        tx_id = str(row.get("transaction_id", "")).strip()
        if not tx_id or tx_id.lower() == "nan":
            report.errors.append(f"Row {row_num}: Missing transaction_id.")
            report.is_valid = False
            continue

        # Date validation
        try:
            tx_date = parse_date(row.get("date"))
        except Exception as exc:
            report.errors.append(f"Row {row_num} ({tx_id}): {exc}")
            report.is_valid = False
            continue

        # Type validation
        tx_type = str(row.get("type", "")).strip().upper()
        if tx_type not in VALID_TX_TYPES:
            report.errors.append(f"Row {row_num} ({tx_id}): Invalid type '{tx_type}'. Must be PAYMENT or REFUND.")
            report.is_valid = False

        # Status validation
        tx_status = str(row.get("status", "")).strip().upper()
        if tx_status not in VALID_TX_STATUSES:
            report.warnings.append(f"Row {row_num} ({tx_id}): Unrecognized status '{tx_status}'.")

        # Monetary fields validation
        try:
            gross = to_decimal(row.get("gross_amount"))
            fee = to_decimal(row.get("fee_amount"))
            net = to_decimal(row.get("net_amount"))
        except Exception as exc:
            report.errors.append(f"Row {row_num} ({tx_id}): Monetary parse error: {exc}")
            report.is_valid = False
            continue

        # Consistency checks
        if tx_type == "PAYMENT" and gross < Decimal("0.00"):
            report.errors.append(f"Row {row_num} ({tx_id}): PAYMENT gross amount cannot be negative.")
            report.is_valid = False

        if tx_type == "REFUND" and gross > Decimal("0.00"):
            report.warnings.append(f"Row {row_num} ({tx_id}): REFUND gross amount is positive ({gross}). Adjusting to negative.")
            gross = -gross
            net = -abs(net)

        ref_id = str(row.get("reference_id", "")).strip() if pd.notna(row.get("reference_id")) else None
        if ref_id in ("", "None", "nan", "NULL"):
            ref_id = None

        parsed.append(
            Transaction(
                transaction_id=tx_id,
                date=tx_date,
                type=tx_type,
                status=tx_status,
                gross_amount=gross,
                fee_amount=fee,
                net_amount=net,
                currency=str(row.get("currency", "USD")).strip().upper() or "USD",
                customer_id=str(row.get("customer_id", "")).strip(),
                payment_method=str(row.get("payment_method", "CREDIT_CARD")).strip(),
                reference_id=ref_id,
                description=str(row.get("description", "")).strip(),
                raw_row=row_num,
            )
        )

    report.parsed_transactions = parsed
    return report


def validate_settlements(df: pd.DataFrame) -> ValidationReport:
    """Validate bank settlements statement DataFrame."""
    report = ValidationReport(dataset_name="Bank Settlements", is_valid=True, total_rows=len(df))

    # 1. Check required columns
    missing_cols = REQUIRED_SETTLEMENT_COLS - set(df.columns)
    if missing_cols:
        report.is_valid = False
        report.errors.append(f"Missing required columns: {sorted(list(missing_cols))}")
        return report

    parsed: List[Settlement] = []

    for idx, row in df.iterrows():
        row_num = idx + 1
        st_id = str(row.get("settlement_id", "")).strip()
        tx_id = str(row.get("transaction_id", "")).strip()

        if not st_id or st_id.lower() == "nan":
            report.errors.append(f"Row {row_num}: Missing settlement_id.")
            report.is_valid = False
            continue

        if not tx_id or tx_id.lower() == "nan":
            report.errors.append(f"Row {row_num} ({st_id}): Missing transaction_id.")
            report.is_valid = False
            continue

        # Date validation
        try:
            st_date = parse_date(row.get("settlement_date"))
        except Exception as exc:
            report.errors.append(f"Row {row_num} ({st_id}): {exc}")
            report.is_valid = False
            continue

        # Type validation
        st_type = str(row.get("type", "")).strip().upper()
        if st_type not in VALID_SETTLEMENT_TYPES:
            report.errors.append(f"Row {row_num} ({st_id}): Invalid settlement type '{st_type}'. Must be CREDIT or DEBIT.")
            report.is_valid = False

        # Monetary fields validation
        try:
            gross = to_decimal(row.get("gross_amount"))
            fee = to_decimal(row.get("fee_amount"))
            net = to_decimal(row.get("net_amount"))
        except Exception as exc:
            report.errors.append(f"Row {row_num} ({st_id}): Monetary parse error: {exc}")
            report.is_valid = False
            continue

        parsed.append(
            Settlement(
                settlement_id=st_id,
                settlement_date=st_date,
                transaction_id=tx_id,
                type=st_type,
                gross_amount=gross,
                fee_amount=fee,
                net_amount=net,
                currency=str(row.get("currency", "USD")).strip().upper() or "USD",
                bank_batch_id=str(row.get("bank_batch_id", "")).strip(),
                raw_row=row_num,
            )
        )

    report.parsed_settlements = parsed
    return report
