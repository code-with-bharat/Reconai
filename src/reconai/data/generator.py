"""Deterministic synthetic data generator planting realistic payments and discrepancies."""

from __future__ import annotations

import csv
import datetime
from decimal import Decimal
from pathlib import Path
import random
from typing import Dict, List, Optional, Tuple

from reconai.engine.financial import (
    DEFAULT_FEE_RATE,
    DEFAULT_FIXED_FEE,
    PENNY,
    ZERO,
    calculate_aggregate_fee,
    calculate_net_amount,
    calculate_per_transaction_fee,
    to_decimal,
)


def generate_synthetic_data(
    seed: int = 42,
    base_year: int = 2026,
    base_month: int = 11,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, any]]:
    """Generate transactions and bank settlement records with 4 deliberate discrepancies.

    Returns:
        (transactions_records, settlements_records, metadata_about_discrepancies)
    """
    random.seed(seed)

    transactions: List[Dict[str, str]] = []
    settlements: List[Dict[str, str]] = []

    customers = [f"CUST-{1000 + i}" for i in range(40)]
    payment_methods = ["CREDIT_CARD", "DEBIT_CARD", "ACH", "APPLE_PAY"]

    current_tx_seq = 1

    def make_tx_id(seq: int) -> str:
        return f"TX-{base_year}-{base_month:02d}-{seq:04d}"

    def make_settle_id(seq: int) -> str:
        return f"STL-{base_year}-{base_month:02d}-{seq:04d}"

    # -------------------------------------------------------------
    # 1. Clean Matched Transactions (Nov 1 to Nov 27)
    # -------------------------------------------------------------
    matched_count = 110
    for i in range(matched_count):
        tx_id = make_tx_id(current_tx_seq)
        settle_id = make_settle_id(current_tx_seq)
        current_tx_seq += 1

        day = random.randint(1, 26)
        tx_date = datetime.date(base_year, base_month, day)
        settle_delay = random.choice([1, 2])
        settle_date = tx_date + datetime.timedelta(days=settle_delay)

        # Dollar amount between $12.00 and $850.00
        gross_cents = random.randint(1200, 85000)
        gross = (Decimal(gross_cents) / Decimal("100")).quantize(PENNY)
        fee = calculate_per_transaction_fee(gross)
        net = calculate_net_amount(gross, fee)

        cust = random.choice(customers)
        pm = random.choice(payment_methods)

        transactions.append({
            "transaction_id": tx_id,
            "date": tx_date.isoformat(),
            "type": "PAYMENT",
            "status": "SUCCESS",
            "gross_amount": f"{gross:.2f}",
            "fee_amount": f"{fee:.2f}",
            "net_amount": f"{net:.2f}",
            "currency": "USD",
            "customer_id": cust,
            "payment_method": pm,
            "reference_id": "",
            "description": f"Standard payment {pm} - {cust}",
        })

        settlements.append({
            "settlement_id": settle_id,
            "settlement_date": settle_date.isoformat(),
            "transaction_id": tx_id,
            "type": "CREDIT",
            "gross_amount": f"{gross:.2f}",
            "fee_amount": f"{fee:.2f}",
            "net_amount": f"{net:.2f}",
            "currency": "USD",
            "bank_batch_id": f"BATCH-{settle_date.strftime('%Y%m%d')}-01",
        })

    # -------------------------------------------------------------
    # 2. Legitimate Valid Refund (Referencing an existing transaction)
    # -------------------------------------------------------------
    parent_tx = transactions[10]
    refund_tx_id = f"REF-{base_year}-{base_month:02d}-0001"
    refund_stl_id = f"STL-REF-{base_year}-{base_month:02d}-0001"
    refund_date = datetime.date(base_year, base_month, 15)
    refund_gross = -to_decimal(parent_tx["gross_amount"])
    refund_fee = Decimal("0.00")
    refund_net = refund_gross

    transactions.append({
        "transaction_id": refund_tx_id,
        "date": refund_date.isoformat(),
        "type": "REFUND",
        "status": "SUCCESS",
        "gross_amount": f"{refund_gross:.2f}",
        "fee_amount": f"{refund_fee:.2f}",
        "net_amount": f"{refund_net:.2f}",
        "currency": "USD",
        "customer_id": parent_tx["customer_id"],
        "payment_method": parent_tx["payment_method"],
        "reference_id": parent_tx["transaction_id"],
        "description": f"Customer refund referencing {parent_tx['transaction_id']}",
    })

    settlements.append({
        "settlement_id": refund_stl_id,
        "settlement_date": (refund_date + datetime.timedelta(days=1)).isoformat(),
        "transaction_id": refund_tx_id,
        "type": "DEBIT",
        "gross_amount": f"{refund_gross:.2f}",
        "fee_amount": f"{refund_fee:.2f}",
        "net_amount": f"{refund_net:.2f}",
        "currency": "USD",
        "bank_batch_id": f"BATCH-{refund_date.strftime('%Y%m%d')}-02",
    })

    # -------------------------------------------------------------
    # Discrepancy 1: Timing Differences (Nov transactions settled in Dec)
    # -------------------------------------------------------------
    timing_diff_txs = []
    for day in (29, 30):
        for _ in range(2):
            tx_id = make_tx_id(current_tx_seq)
            settle_id = make_settle_id(current_tx_seq)
            current_tx_seq += 1

            tx_date = datetime.date(base_year, base_month, day)
            # Settles on Dec 1 or Dec 2 of next month
            settle_date = datetime.date(base_year, base_month + 1, (day - 28))

            gross = Decimal("145.50") if day == 29 else Decimal("280.00")
            fee = calculate_per_transaction_fee(gross)
            net = calculate_net_amount(gross, fee)

            cust = random.choice(customers)

            transactions.append({
                "transaction_id": tx_id,
                "date": tx_date.isoformat(),
                "type": "PAYMENT",
                "status": "SUCCESS",
                "gross_amount": f"{gross:.2f}",
                "fee_amount": f"{fee:.2f}",
                "net_amount": f"{net:.2f}",
                "currency": "USD",
                "customer_id": cust,
                "payment_method": "CREDIT_CARD",
                "reference_id": "",
                "description": "Late month transaction settled next month",
            })

            settlements.append({
                "settlement_id": settle_id,
                "settlement_date": settle_date.isoformat(),
                "transaction_id": tx_id,
                "type": "CREDIT",
                "gross_amount": f"{gross:.2f}",
                "fee_amount": f"{fee:.2f}",
                "net_amount": f"{net:.2f}",
                "currency": "USD",
                "bank_batch_id": f"BATCH-{settle_date.strftime('%Y%m%d')}-01",
            })
            timing_diff_txs.append(tx_id)

    # -------------------------------------------------------------
    # Discrepancy 2: Rounding Difference (Per-transaction vs aggregate fee rounding)
    # -------------------------------------------------------------
    # We construct a batch of 8 transactions where per-transaction fee sum differs
    # from aggregate fee by exactly $0.02.
    rnd_gross_amounts = [
        Decimal("45.15"), Decimal("67.89"), Decimal("120.35"), Decimal("89.44"),
        Decimal("15.67"), Decimal("210.50"), Decimal("34.99"), Decimal("78.20")
    ]
    sum_per_tx_fees, agg_fee, rounding_diff = calculate_aggregate_fee(rnd_gross_amounts)

    # In our transactions ledger, each transaction records its per-transaction rounded fee.
    # In the bank settlement, one designated settlement in this batch absorbs the aggregate rounding difference
    # (or the bank settles with fee = aggregate fee distributed).
    rounding_tx_ids = []
    rnd_batch_id = f"BATCH-{base_year}{base_month:02d}18-AGG-FEE"

    for idx, gross in enumerate(rnd_gross_amounts):
        tx_id = make_tx_id(current_tx_seq)
        settle_id = make_settle_id(current_tx_seq)
        current_tx_seq += 1

        tx_date = datetime.date(base_year, base_month, 18)
        settle_date = datetime.date(base_year, base_month, 19)

        per_tx_fee = calculate_per_transaction_fee(gross)
        ledger_net = calculate_net_amount(gross, per_tx_fee)

        # Plant the rounding difference on the last transaction in the batch
        if idx == len(rnd_gross_amounts) - 1:
            # Bank settlement reflects aggregate fee rounding adjustment
            # Here rounding_diff is -0.01 (sum_per_tx=21.59, agg_fee=21.60 -> bank fee higher by 0.01)
            # So bank fee is per_tx_fee - rounding_diff = per_tx_fee + 0.01
            bank_fee = (per_tx_fee - rounding_diff).quantize(PENNY)
            bank_net = calculate_net_amount(gross, bank_fee)
            planted_rounding_tx_id = tx_id
        else:
            bank_fee = per_tx_fee
            bank_net = ledger_net

        transactions.append({
            "transaction_id": tx_id,
            "date": tx_date.isoformat(),
            "type": "PAYMENT",
            "status": "SUCCESS",
            "gross_amount": f"{gross:.2f}",
            "fee_amount": f"{per_tx_fee:.2f}",
            "net_amount": f"{ledger_net:.2f}",
            "currency": "USD",
            "customer_id": "CUST-RETAIL-CORP",
            "payment_method": "CREDIT_CARD",
            "reference_id": "",
            "description": f"Merchant batch transaction {idx+1}/{len(rnd_gross_amounts)}",
        })

        settlements.append({
            "settlement_id": settle_id,
            "settlement_date": settle_date.isoformat(),
            "transaction_id": tx_id,
            "type": "CREDIT",
            "gross_amount": f"{gross:.2f}",
            "fee_amount": f"{bank_fee:.2f}",
            "net_amount": f"{bank_net:.2f}",
            "currency": "USD",
            "bank_batch_id": rnd_batch_id,
        })
        rounding_tx_ids.append(tx_id)

    # -------------------------------------------------------------
    # Discrepancy 3: Duplicate Record in Bank Settlements
    # -------------------------------------------------------------
    # Pick an existing settlement in November and plant a duplicate row in bank_settlements.csv
    target_settlement = settlements[25]
    dup_settlement_id = f"{target_settlement['settlement_id']}-DUP"
    duplicate_record = {
        "settlement_id": dup_settlement_id,
        "settlement_date": target_settlement["settlement_date"],
        "transaction_id": target_settlement["transaction_id"],
        "type": target_settlement["type"],
        "gross_amount": target_settlement["gross_amount"],
        "fee_amount": target_settlement["fee_amount"],
        "net_amount": target_settlement["net_amount"],
        "currency": target_settlement["currency"],
        "bank_batch_id": f"{target_settlement['bank_batch_id']}-RETRY",
    }
    settlements.append(duplicate_record)
    planted_duplicate_tx_id = target_settlement["transaction_id"]

    # -------------------------------------------------------------
    # Discrepancy 4: Orphan Refund (Referencing nonexistent original transaction)
    # -------------------------------------------------------------
    orphan_tx_id = f"REF-{base_year}-{base_month:02d}-9999"
    orphan_date = datetime.date(base_year, base_month, 22)
    orphan_gross = Decimal("-175.00")
    orphan_fee = Decimal("0.00")
    orphan_net = orphan_gross

    transactions.append({
        "transaction_id": orphan_tx_id,
        "date": orphan_date.isoformat(),
        "type": "REFUND",
        "status": "SUCCESS",
        "gross_amount": f"{orphan_gross:.2f}",
        "fee_amount": f"{orphan_fee:.2f}",
        "net_amount": f"{orphan_net:.2f}",
        "currency": "USD",
        "customer_id": "CUST-UNKNOWN",
        "payment_method": "CREDIT_CARD",
        "reference_id": "TX-NONEXISTENT-ORIGIN-0000",
        "description": "Customer manual refund referencing invalid parent TX-NONEXISTENT-ORIGIN-0000",
    })
    planted_orphan_tx_id = orphan_tx_id

    # -------------------------------------------------------------
    # 5. Realistic Unmatched Items (To exercise complete reconciliation)
    # -------------------------------------------------------------
    # Unmatched Transaction (e.g. gateway timeout or pending settlement)
    unmatched_tx_id = make_tx_id(current_tx_seq)
    current_tx_seq += 1
    transactions.append({
        "transaction_id": unmatched_tx_id,
        "date": datetime.date(base_year, base_month, 12).isoformat(),
        "type": "PAYMENT",
        "status": "SUCCESS",
        "gross_amount": "315.00",
        "fee_amount": "9.44",
        "net_amount": "305.56",
        "currency": "USD",
        "customer_id": "CUST-1044",
        "payment_method": "ACH",
        "reference_id": "",
        "description": "Direct ACH payment pending bank transmission",
    })

    # Unmatched Settlement (e.g. monthly bank account interest credit or fee reversal)
    unmatched_stl_id = f"STL-ADJ-{base_year}-{base_month:02d}-001"
    settlements.append({
        "settlement_id": unmatched_stl_id,
        "settlement_date": datetime.date(base_year, base_month, 25).isoformat(),
        "transaction_id": "BANK-DIRECT-CREDIT-7788",
        "type": "CREDIT",
        "gross_amount": "50.00",
        "fee_amount": "0.00",
        "net_amount": "50.00",
        "currency": "USD",
        "bank_batch_id": f"BATCH-{base_year}{base_month:02d}25-BANK-INT",
    })

    metadata = {
        "timing_difference_tx_ids": timing_diff_txs,
        "rounding_difference_tx_id": planted_rounding_tx_id,
        "rounding_batch_id": rnd_batch_id,
        "rounding_diff_amount": str(rounding_diff),
        "sum_per_tx_fees": str(sum_per_tx_fees),
        "agg_fee": str(agg_fee),
        "duplicate_tx_id": planted_duplicate_tx_id,
        "duplicate_settlement_id": dup_settlement_id,
        "orphan_refund_tx_id": planted_orphan_tx_id,
        "unmatched_tx_id": unmatched_tx_id,
        "unmatched_settlement_id": unmatched_stl_id,
    }

    return transactions, settlements, metadata


def save_synthetic_data_csv(
    transactions: List[Dict[str, str]],
    settlements: List[Dict[str, str]],
    output_dir: str | Path,
) -> Tuple[Path, Path]:
    """Save synthetic data records to CSV files."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    tx_file = out_path / "transactions.csv"
    stl_file = out_path / "bank_settlements.csv"

    if transactions:
        tx_keys = list(transactions[0].keys())
        with open(tx_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=tx_keys)
            writer.writeheader()
            writer.writerows(transactions)

    if settlements:
        stl_keys = list(settlements[0].keys())
        with open(stl_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=stl_keys)
            writer.writeheader()
            writer.writerows(settlements)

    return tx_file, stl_file


if __name__ == "__main__":
    txs, stls, meta = generate_synthetic_data()
    save_synthetic_data_csv(txs, stls, Path(__file__).resolve().parent.parent.parent.parent / "sample_data")
    print(f"Generated {len(txs)} transactions and {len(stls)} settlements.")
