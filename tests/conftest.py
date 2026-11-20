"""Test configuration and shared fixtures for ReconAI test suite."""

import sys
from pathlib import Path
import pytest

# Add src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reconai.data.generator import generate_synthetic_data
from reconai.data.validator import validate_settlements, validate_transactions
import pandas as pd


@pytest.fixture
def sample_raw_data():
    """Return synthetic raw records and planted discrepancy metadata."""
    txs, stls, meta = generate_synthetic_data(seed=42)
    return txs, stls, meta


@pytest.fixture
def validated_data(sample_raw_data):
    """Return validated Transaction and Settlement domain objects."""
    txs, stls, meta = sample_raw_data
    df_tx = pd.DataFrame(txs)
    df_stl = pd.DataFrame(stls)

    val_tx = validate_transactions(df_tx)
    val_stl = validate_settlements(df_stl)

    assert val_tx.is_valid
    assert val_stl.is_valid

    return val_tx.parsed_transactions, val_stl.parsed_settlements, meta
