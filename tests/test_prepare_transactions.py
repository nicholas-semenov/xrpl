"""Synthetic toy cases for units, issuer identity, conversions and safe joins."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal
import pyarrow as pa

from feature_workspace.prepare_transactions import (COLUMNS, XRP_SENTINEL, prepare_transactions,
                                                     summarize, write_table_once)

USD_A = "issuerA:USD"
USD_B = "issuerB:USD"
EUR_B = "issuerB:EUR"


def wire_amount(asset, value):
    if asset == "XRP":
        return str(round(value * 1_000_000))
    issuer, currency = asset.split(":")
    return {"issuer": issuer, "currency": currency, "value": f"{value:.6f}"}


def fixture(paths, timestamps=None):
    """Build only toy ledger records, never fabricated findings about supplied data."""
    transactions, transfers = [], []
    for i, (hash_, path) in enumerate(paths.items()):
        timestamp = timestamps[i] if timestamps else 3599
        metadata = {"TRANSACTION_HASH": hash_, "TIMESTAMP": timestamp, "LEDGER_INDEX": 100 + i,
                    "LEDGER_HASH": f"ledger{i}", "TRANSACTION_INDEX": 0}
        destination = path[-1][1]
        delivered = wire_amount(path[-1][2], path[-1][3])
        transactions.append({**metadata, "ACCOUNT": path[0][0], "TRANSACTION_TYPE": "Payment",
                             "SUCCESS": True, "SOURCE_FEE": 10, "FEE": 0.00001,
                             "DELIVERED_AMOUNT": json.dumps(delivered),
                             "EXTRA_TRANSACTION_FIELDS": json.dumps({"Destination": destination,
                                 "Amount": delivered, "SendMax": wire_amount(path[0][2], 999999.)})})
        for index, (sender, receiver, asset, amount) in enumerate(path):
            issuer, symbol = (XRP_SENTINEL, "XRP") if asset == "XRP" else asset.split(":")
            transfers.append({**metadata, "TRANSFER_INDEX": index, "FROM_ADDRESS": sender,
                              "TO_ADDRESS": receiver, "TOKEN_ADDRESS": issuer, "SYMBOL": symbol,
                              "TRANSFER_TYPE": "direct_payment" if len(path) == 1 else "path_payment",
                              "SOURCE_VALUE": round(amount * 1e6) if asset == "XRP" else amount,
                              "VALUE": amount})
    rates = pd.DataFrame([{"TIMESTAMP": hour, "ASSET": asset, "PRICE_MICRO_USD": price}
                          for hour in [0, 3600] for asset, price in
                          [("XRP", 500000 if hour == 0 else 750000),
                           (USD_A, 1100000), (USD_B, 1200000), (EUR_B, 1300000)]])
    return pd.DataFrame(transactions), pd.DataFrame(transfers), rates


class TransactionPreparationTests(unittest.TestCase):
    def test_xrp_units_original_order_and_non_mutating_inputs(self):
        tx, legs, rates = fixture({"z": [("S", "D", "XRP", 1.)],
                                   "a": [("A", "B", USD_A, 10.)]})
        originals = [deepcopy(x) for x in (tx, legs, rates)]
        result = prepare_transactions(tx, legs.iloc[::-1], rates)
        self.assertEqual(result.columns.tolist(), COLUMNS)
        self.assertEqual(result.TRANSACTION_HASH.tolist(), ["z", "a"])
        self.assertEqual(result.SOURCE_AMOUNT.tolist(), [1., 10.])
        self.assertEqual(result.SOURCE_AMOUNT_USD.tolist(), [0.5, 11.])
        self.assertEqual(result.FEE_XRP.tolist(), [0.00001, 0.00001])
        self.assertEqual(result.INTERMEDIARY_COUNT.tolist(), [0, 0])
        for original, after in zip(originals, (tx, legs, rates)):
            assert_frame_equal(original, after)

    def test_bridge_uses_executed_endpoints_separate_rates_and_ignores_sendmax(self):
        tx, legs, rates = fixture({"bridge": [("S", "LP1", USD_A, 10.),
                                               ("LP1", "LP2", "XRP", 20.),
                                               ("LP2", "D", EUR_B, 8.)]})
        result = prepare_transactions(tx, legs.sample(frac=1, random_state=4), rates).iloc[0]
        self.assertEqual(result.SENDER, "S")
        self.assertEqual(result.RECEIVER, "D")
        self.assertEqual(result.SOURCE_AMOUNT, 10.)  # SendMax is 999999, not actual cost.
        self.assertEqual(result.DESTINATION_AMOUNT, 8.)
        self.assertEqual(result.SOURCE_AMOUNT_USD, 11.)
        self.assertAlmostEqual(result.DESTINATION_AMOUNT_USD, 10.4)
        self.assertEqual(result.TRANSFER_COUNT, 3)
        self.assertEqual(result.CONVERSION_STEP_COUNT, 2)
        self.assertEqual(result.INTERMEDIARY_COUNT, 2)
        self.assertTrue(result.IS_CONVERSION)
        with self.assertRaisesRegex(ValueError, "Missing destination asset/hour rate"):
            prepare_transactions(tx, legs, rates.loc[rates.ASSET.ne(EUR_B)])

    def test_extra_same_asset_leg_is_not_a_conversion(self):
        tx, legs, rates = fixture({"relay": [("S", "M", "XRP", 1.), ("M", "D", "XRP", .99)]})
        row = prepare_transactions(tx, legs, rates).iloc[0]
        self.assertEqual(row.TRANSFER_COUNT, 2)
        self.assertEqual(row.CONVERSION_STEP_COUNT, 0)
        self.assertFalse(row.IS_CONVERSION)
        self.assertEqual(row.INTERMEDIARY_COUNT, 1)

    def test_same_symbol_different_issuers_is_asset_change(self):
        tx, legs, rates = fixture({"issuer_swap": [("S", "LP", USD_A, 10.), ("LP", "D", USD_B, 9.)]})
        row = prepare_transactions(tx, legs, rates).iloc[0]
        self.assertEqual(row.SOURCE_ASSET, USD_A)
        self.assertEqual(row.DESTINATION_ASSET, USD_B)
        self.assertEqual(row.CONVERSION_STEP_COUNT, 1)
        self.assertAlmostEqual(row.DESTINATION_AMOUNT_USD, 10.8)

    def test_return_to_original_asset_still_counts_two_changes(self):
        tx, legs, rates = fixture({"roundtrip": [("S", "LP1", USD_A, 10.),
                                                  ("LP1", "LP2", "XRP", 20.),
                                                  ("LP2", "D", USD_A, 9.9)]})
        row = prepare_transactions(tx, legs, rates).iloc[0]
        self.assertEqual(row.SOURCE_ASSET, row.DESTINATION_ASSET)
        self.assertTrue(row.IS_CONVERSION)
        self.assertEqual(row.CONVERSION_STEP_COUNT, 2)

    def test_containing_utc_hour_and_missing_or_duplicate_rates_fail(self):
        tx, legs, rates = fixture({"before": [("A", "B", "XRP", 1.)],
                                   "boundary": [("C", "D", "XRP", 1.)]}, [3599, 3600])
        self.assertEqual(prepare_transactions(tx, legs, rates).SOURCE_AMOUNT_USD.tolist(), [.5, .75])
        with self.assertRaisesRegex(ValueError, "Missing source asset/hour rate"):
            prepare_transactions(tx, legs, rates.loc[rates.TIMESTAMP.eq(0)])
        with self.assertRaisesRegex(ValueError, "Duplicate hourly asset rates"):
            prepare_transactions(tx, legs, pd.concat([rates, rates.iloc[:1]]))

    def test_bad_joins_paths_units_or_delivered_values_fail_instead_of_dropping(self):
        tx, legs, rates = fixture({"x": [("S", "LP", "XRP", 1.), ("LP", "D", USD_A, .4)]})
        cases = []
        cases.append((pd.concat([tx, tx]), legs, "Transaction hashes"))
        cases.append((tx, pd.concat([legs, legs.iloc[:1]]), "Duplicate leg key"))
        cases.append((tx, legs.iloc[:0], "Transfer coverage"))
        bad = legs.copy(); bad.loc[1, "TRANSFER_INDEX"] = 2
        cases.append((tx, bad, "contiguous"))
        bad = legs.copy(); bad.loc[1, "FROM_ADDRESS"] = "unrelated"
        cases.append((tx, bad, "continuous"))
        bad = legs.copy(); bad.loc[0, "VALUE"] /= 1_000_000
        cases.append((tx, bad, "normalization"))
        bad = tx.copy(); bad.loc[0, "DELIVERED_AMOUNT"] = json.dumps(wire_amount(USD_A, .5))
        cases.append((bad, legs, "destination amount"))
        bad = tx.copy(); bad.loc[0, "SUCCESS"] = False
        cases.append((bad, legs, "successful payments"))
        for bad_tx, bad_legs, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                prepare_transactions(bad_tx, bad_legs, rates)

    def test_summary_counts_actual_changes(self):
        tx, legs, rates = fixture({"direct": [("A", "B", "XRP", 1.)],
                                   "same": [("A", "M", "XRP", 1.), ("M", "B", "XRP", .9)],
                                   "one": [("C", "L", USD_A, 10.), ("L", "D", USD_B, 9.)],
                                   "two": [("E", "N", USD_A, 10.), ("N", "O", "XRP", 20.),
                                           ("O", "F", USD_A, 9.9)]})
        s = summarize(prepare_transactions(tx, legs, rates))
        self.assertEqual(s["total_transactions"], 4)
        self.assertEqual(s["conversion_transactions"], 2)
        self.assertEqual(s["total_conversion_steps"], 3)
        self.assertEqual(s["non_conversion_transactions"], 2)
        self.assertEqual(s["conversion_step_distribution"], {"0": 2, "1": 1, "2": 1})
        self.assertEqual(s["conversion_percentage"], 50.)
        self.assertEqual(s["same_endpoint_asset_with_conversion"], 1)
        self.assertEqual(sum(p["count"] for p in s["most_common_conversion_asset_pairs"]), 2)

    def test_existing_artifact_cannot_be_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "table.parquet"
            table = pa.table({"id": [1, 2]})
            write_table_once(table, path)
            write_table_once(table, path)
            with self.assertRaisesRegex(ValueError, "Existing artifact differs"):
                write_table_once(pa.table({"id": [3]}), path)


if __name__ == "__main__":
    unittest.main()
