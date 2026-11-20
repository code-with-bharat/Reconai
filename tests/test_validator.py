"""Tests for input validation and schema verification."""

import pandas as pd
from decimal import Decimal

from reconai.data.validator import (
    validate_settlements,
    validate_transactions,
)


def test_validate_valid_datasets(sample_raw_data):
    """Verify clean dataset passes validation with is_valid == True."""
    txs, stls, _ = sample_raw_data
    df_tx = pd.DataFrame(txs)
    df_stl = pd.DataFrame(stls)

    report_tx = validate_transactions(df_tx)
    report_stl = validate_settlements(df_stl)

    assert report_tx.is_valid
    assert len(report_tx.errors) == 0
    assert len(report_tx.parsed_transactions) == len(txs)

    assert report_stl.is_valid
    assert len(report_stl.errors) == 0
    assert len(report_stl.parsed_settlements) == len(stls)


def test_validate_transactions_missing_columns():
    """Verify validator catches missing mandatory columns."""
    df_bad = pd.DataFrame([{"transaction_id": "TX-1", "gross_amount": "100.00"}])
    report = validate_transactions(df_bad)

    assert not report.is_valid
    assert any("Missing required columns" in err for err in report.errors)


def test_validate_settlements_missing_columns():
    """Verify validator catches missing mandatory settlement columns."""
    df_bad = pd.DataFrame([{"settlement_id": "STL-1", "gross_amount": "100.00"}])
    report = validate_settlements(df_bad)

    assert not report.is_valid
    assert any("Missing required columns" in err for err in report.errors)


def test_validate_invalid_date_format():
    """Verify corrupt date values are flagged as errors."""
    df_bad = pd.DataFrame([{
        "transaction_id": "TX-99",
        "date": "invalid-date",
        "type": "PAYMENT",
        "status": "SUCCESS",
        "gross_amount": "100.00",
        "fee_amount": "3.20",
        "net_amount": "96.80",
    }])
    report = validate_transactions(df_bad)
    assert not report.is_valid
    assert any("Invalid date format" in err for err in report.errors)


def test_validate_invalid_monetary_format():
    """Verify corrupt monetary values are flagged as errors."""
    df_bad = pd.DataFrame([{
        "transaction_id": "TX-99",
        "date": "2026-11-01",
        "type": "PAYMENT",
        "status": "SUCCESS",
        "gross_amount": "not_a_number",
        "fee_amount": "3.20",
        "net_amount": "96.80",
    }])
    report = validate_transactions(df_bad)
    assert not report.is_valid
    assert any("Monetary parse error" in err for err in report.errors)
