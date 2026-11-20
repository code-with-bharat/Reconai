"""Tests for synthetic data generation and planted discrepancy verification."""

from pathlib import Path
from decimal import Decimal
import pandas as pd

from reconai.data.generator import generate_synthetic_data, save_synthetic_data_csv


def test_generator_deterministic_output():
    """Verify seed=42 produces identical deterministic output across calls."""
    tx1, stl1, meta1 = generate_synthetic_data(seed=42)
    tx2, stl2, meta2 = generate_synthetic_data(seed=42)

    assert len(tx1) == len(tx2)
    assert len(stl1) == len(stl2)
    assert tx1[0] == tx2[0]
    assert stl1[0] == stl2[0]
    assert meta1 == meta2


def test_planted_discrepancies_exist(sample_raw_data):
    """Verify all 4 required discrepancies are present in the generated dataset."""
    txs, stls, meta = sample_raw_data

    # 1. November transactions settled in December
    timing_tx_ids = meta["timing_difference_tx_ids"]
    assert len(timing_tx_ids) >= 2
    for tx_id in timing_tx_ids:
        tx_row = next(t for t in txs if t["transaction_id"] == tx_id)
        stl_row = next(s for s in stls if s["transaction_id"] == tx_id)
        assert tx_row["date"].startswith("2026-11")
        assert stl_row["settlement_date"].startswith("2026-12")

    # 2. Rounding difference caused by per-transaction vs aggregate fee rounding
    rnd_tx_id = meta["rounding_difference_tx_id"]
    rnd_tx = next(t for t in txs if t["transaction_id"] == rnd_tx_id)
    rnd_stl = next(s for s in stls if s["transaction_id"] == rnd_tx_id)
    assert rnd_tx["gross_amount"] == rnd_stl["gross_amount"]
    assert rnd_tx["fee_amount"] != rnd_stl["fee_amount"]
    assert rnd_tx["net_amount"] != rnd_stl["net_amount"]
    diff = Decimal(rnd_stl["net_amount"]) - Decimal(rnd_tx["net_amount"])
    assert diff != Decimal("0.00")

    # 3. Duplicate record in bank settlements
    dup_tx_id = meta["duplicate_tx_id"]
    stls_for_tx = [s for s in stls if s["transaction_id"] == dup_tx_id]
    assert len(stls_for_tx) >= 2, "Expected duplicate settlement records for the same transaction ID"

    # 4. Orphan refund referencing nonexistent original transaction
    orphan_id = meta["orphan_refund_tx_id"]
    orphan_tx = next(t for t in txs if t["transaction_id"] == orphan_id)
    assert orphan_tx["type"] == "REFUND"
    parent_ref = orphan_tx["reference_id"]
    assert parent_ref != ""
    # Ensure parent does not exist in transactions ledger
    parent_exists = any(t["transaction_id"] == parent_ref for t in txs)
    assert not parent_exists, f"Parent ID {parent_ref} should not exist in transactions ledger"


def test_save_synthetic_data_csv(tmp_path):
    """Verify CSV persistence and structure."""
    txs, stls, _ = generate_synthetic_data(seed=42)
    tx_file, stl_file = save_synthetic_data_csv(txs, stls, tmp_path)

    assert tx_file.exists()
    assert stl_file.exists()

    df_tx = pd.read_csv(tx_file)
    df_stl = pd.read_csv(stl_file)

    assert len(df_tx) == len(txs)
    assert len(df_stl) == len(stls)
    assert "transaction_id" in df_tx.columns
    assert "settlement_id" in df_stl.columns
