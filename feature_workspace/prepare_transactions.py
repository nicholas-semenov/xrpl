"""Reconstruct label-free transaction tables from ordered executed transfer legs.

Run: .venv/bin/python -m feature_workspace.prepare_transactions
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shlex

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from feature_workspace.paths import REPO_ROOT, output_path

SCALE = 1_000_000
XRP_SENTINEL = "0x1111222211112222111122221111222211112222"
SPLITS = {"train": REPO_ROOT / "data/traning_data/train",
          "validation": REPO_ROOT / "data/traning_data/validation",
          "test": REPO_ROOT / "data/test_data"}
COLUMNS = ["TRANSACTION_HASH", "TIMESTAMP", "SENDER", "RECEIVER", "SOURCE_ASSET", "SOURCE_AMOUNT",
           "DESTINATION_ASSET", "DESTINATION_AMOUNT", "SOURCE_AMOUNT_USD", "DESTINATION_AMOUNT_USD",
           "TRANSFER_COUNT", "IS_CONVERSION", "CONVERSION_STEP_COUNT", "INTERMEDIARY_COUNT", "FEE_XRP"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer_values(series: pd.Series, name: str) -> pd.Series:
    """Reject fractional or missing values instead of silently truncating them."""
    require(series.notna().all(), f"Missing {name}")
    result = series.astype("int64")
    require(series.eq(result).all(), f"Non-integral {name}")
    return result


def decode_delivered(wire: str) -> tuple[str, float]:
    """Decode documented JSON XRP drops or issued-token units for cross-checking."""
    amount = json.loads(wire)
    if isinstance(amount, str):
        return "XRP", float(Decimal(amount) / SCALE)
    require(isinstance(amount, dict), "Unsupported delivered amount JSON")
    return f"{amount['issuer']}:{amount['currency']}", float(Decimal(amount["value"]))


def prepare_transactions(transactions: pd.DataFrame, transfers: pd.DataFrame,
                         rates: pd.DataFrame) -> pd.DataFrame:
    """Return the requested 15 columns in original transaction order.

    Read actual amounts from first/last legs, use VALUE only after verifying its
    documented normalization, and count adjacent full asset-identity changes.
    Inputs are never mutated. Unpriced or unreconstructable records fail loudly.
    """
    tx = transactions.copy().reset_index(drop=True)
    legs = transfers.copy()
    prices = rates.copy()
    require(len(tx) > 0, "Empty transaction table")
    require(tx.TRANSACTION_HASH.notna().all() and tx.TRANSACTION_HASH.is_unique,
            "Transaction hashes must be non-null and unique")
    require(tx.TRANSACTION_TYPE.eq("Payment").all() and tx.SUCCESS.eq(True).all(),
            "Only documented successful payments are supported; no silent row dropping")
    require(legs.TRANSACTION_HASH.notna().all() and
            set(legs.TRANSACTION_HASH) == set(tx.TRANSACTION_HASH), "Transfer coverage mismatch")
    require(not legs.duplicated(["TRANSACTION_HASH", "TRANSFER_INDEX"]).any(), "Duplicate leg key")
    tx["TIMESTAMP"] = integer_values(tx.TIMESTAMP, "transaction timestamp")
    legs["TRANSFER_INDEX"] = integer_values(legs.TRANSFER_INDEX, "transfer index")
    legs = legs.sort_values(["TRANSACTION_HASH", "TRANSFER_INDEX"], kind="stable").reset_index(drop=True)
    require(legs.TRANSFER_INDEX.eq(legs.groupby("TRANSACTION_HASH").cumcount()).all(),
            "Transfer indices must be contiguous from zero")
    # Many-to-one leg join is validated before reducing back to the primary tx table.
    metadata = ["TIMESTAMP", "LEDGER_INDEX", "LEDGER_HASH", "TRANSACTION_INDEX"]
    joined = legs.merge(tx[["TRANSACTION_HASH", *metadata]], on="TRANSACTION_HASH",
                        how="left", validate="many_to_one", suffixes=("", "_tx"), sort=False)
    for column in metadata:
        require(joined[column].eq(joined[column + "_tx"]).all(), f"Leg/transaction {column} mismatch")
    for column in ["FROM_ADDRESS", "TO_ADDRESS", "TOKEN_ADDRESS", "SYMBOL", "SOURCE_VALUE", "VALUE"]:
        require(legs[column].notna().all(), f"Missing leg {column}")
    same_tx = legs.TRANSACTION_HASH.eq(legs.TRANSACTION_HASH.shift())
    require(not (same_tx & legs.FROM_ADDRESS.ne(legs.TO_ADDRESS.shift())).any(),
            "Executed legs do not form a continuous ordered path")
    native = legs.SYMBOL.eq("XRP")
    require(legs.loc[native, "TOKEN_ADDRESS"].eq(XRP_SENTINEL).all(), "Unexpected native XRP identifier")
    legs["ASSET"] = np.where(native, "XRP", legs.TOKEN_ADDRESS + ":" + legs.SYMBOL)
    values = legs.VALUE.astype(float)
    source_values = legs.SOURCE_VALUE.astype(float)
    require(np.isfinite(values).all() and values.gt(0).all(), "Invalid normalized leg values")
    require(np.isfinite(source_values).all() and source_values.gt(0).all(), "Invalid source leg values")
    expected_units = np.where(native, source_values / SCALE, source_values)
    require(np.allclose(values, expected_units, rtol=1e-12, atol=1e-12),
            "VALUE normalization inconsistent with SOURCE_VALUE; refuse double conversion")
    require(np.equal(source_values[native], np.floor(source_values[native])).all(), "Non-integral XRP drops")
    legs["AMOUNT"] = values  # Already whole XRP / token units; do not divide VALUE again.
    legs["ASSET_CHANGE"] = same_tx & legs.ASSET.ne(legs.ASSET.shift())
    grouped = legs.groupby("TRANSACTION_HASH", sort=False)
    first = grouped.head(1).set_index("TRANSACTION_HASH").reindex(tx.TRANSACTION_HASH)
    last = grouped.tail(1).set_index("TRANSACTION_HASH").reindex(tx.TRANSACTION_HASH)
    fields = tx.EXTRA_TRANSACTION_FIELDS.map(json.loads)
    destinations = fields.map(lambda f: f["Destination"])
    require(destinations.map(lambda d: isinstance(d, str) and bool(d)).all(), "Invalid destination")
    require(first.FROM_ADDRESS.tolist() == tx.ACCOUNT.tolist(), "Executed source differs from ACCOUNT")
    require(last.TO_ADDRESS.tolist() == destinations.tolist(), "Executed receiver differs from Destination")
    delivered = tx.DELIVERED_AMOUNT.map(decode_delivered)
    require(last.ASSET.tolist() == [a for a, _ in delivered], "Delivered asset mismatch")
    require(np.allclose(last.AMOUNT, [v for _, v in delivered], rtol=1e-12, atol=1e-12),
            "Executed destination amount differs from DELIVERED_AMOUNT")
    counts = grouped.size()
    steps = grouped.ASSET_CHANGE.sum().astype("int64")
    path_wallets = {h: set(g.FROM_ADDRESS) | set(g.TO_ADDRESS) for h, g in grouped}
    fee = integer_values(tx.SOURCE_FEE, "fee drops").astype(float) / SCALE
    require(fee.ge(0).all() and np.isfinite(fee).all(), "Invalid XRP fee")
    require(np.allclose(fee, tx.FEE.astype(float), rtol=1e-12, atol=1e-12), "Fee unit mismatch")
    result = pd.DataFrame({
        "TRANSACTION_HASH": tx.TRANSACTION_HASH, "TIMESTAMP": tx.TIMESTAMP,
        "SENDER": tx.ACCOUNT, "RECEIVER": destinations,
        "SOURCE_ASSET": first.ASSET.to_numpy(), "SOURCE_AMOUNT": first.AMOUNT.to_numpy(),
        "DESTINATION_ASSET": last.ASSET.to_numpy(), "DESTINATION_AMOUNT": last.AMOUNT.to_numpy(),
        "TRANSFER_COUNT": tx.TRANSACTION_HASH.map(counts).astype("int64"),
        "IS_CONVERSION": tx.TRANSACTION_HASH.map(steps).gt(0),
        "CONVERSION_STEP_COUNT": tx.TRANSACTION_HASH.map(steps).astype("int64"),
        "INTERMEDIARY_COUNT": [len(path_wallets[h] - {s, d}) for h, s, d in
                               zip(tx.TRANSACTION_HASH, tx.ACCOUNT, destinations)],
        "FEE_XRP": fee,
    })
    prices["TIMESTAMP"] = integer_values(prices.TIMESTAMP, "price timestamp")
    require(prices.ASSET.notna().all(), "Missing rate asset")
    require(not prices.duplicated(["TIMESTAMP", "ASSET"]).any(), "Duplicate hourly asset rates")
    require(prices.TIMESTAMP.mod(3600).eq(0).all(), "Rates must be UTC-hour aligned")
    price_micro = integer_values(prices.PRICE_MICRO_USD, "micro-USD price")
    require(price_micro.gt(0).all(), "Non-positive rate")
    prices["PRICE_USD"] = price_micro.astype(float) / SCALE
    lookup = prices.set_index(["TIMESTAMP", "ASSET"]).PRICE_USD
    hours = result.TIMESTAMP // 3600 * 3600
    for side in ("SOURCE", "DESTINATION"):
        keys = pd.MultiIndex.from_arrays([hours, result[f"{side}_ASSET"]])
        matched_prices = lookup.reindex(keys)
        require(matched_prices.notna().all(), f"Missing {side.lower()} asset/hour rate")
        result[f"{side}_AMOUNT_USD"] = result[f"{side}_AMOUNT"] * matched_prices.to_numpy()
    result = result.loc[:, COLUMNS]
    require(result.TRANSACTION_HASH.tolist() == tx.TRANSACTION_HASH.tolist(), "Transaction alignment changed")
    require(result.notna().all().all(), "Missing reconstructed values")
    numeric = result.select_dtypes(include="number")
    require(np.isfinite(numeric.to_numpy()).all(), "Non-finite reconstructed values")
    require(result.CONVERSION_STEP_COUNT.lt(result.TRANSFER_COUNT).all(), "Invalid asset change count")
    return result


def summarize(table: pd.DataFrame) -> dict:
    """Count transaction conversions and full-identity source/destination pairs."""
    pairs = table.groupby(["SOURCE_ASSET", "DESTINATION_ASSET"]).size().reset_index(name="count")
    pairs = pairs.sort_values(["count", "SOURCE_ASSET", "DESTINATION_ASSET"], ascending=[False, True, True])
    conversion_pairs = table.loc[table.IS_CONVERSION].groupby(
        ["SOURCE_ASSET", "DESTINATION_ASSET"]).size().reset_index(name="count")
    conversion_pairs = conversion_pairs.sort_values(
        ["count", "SOURCE_ASSET", "DESTINATION_ASSET"], ascending=[False, True, True])
    total = len(table)
    conversions = int(table.IS_CONVERSION.sum())
    return {"total_transactions": total, "conversion_transactions": conversions,
            "total_conversion_steps": int(table.CONVERSION_STEP_COUNT.sum()),
            "non_conversion_transactions": total - conversions,
            "conversion_percentage": 100 * conversions / total,
            "conversion_step_distribution": {str(int(k)): int(v) for k, v in
                table.CONVERSION_STEP_COUNT.value_counts().sort_index().items()},
            "transfer_count_distribution": {str(int(k)): int(v) for k, v in
                table.TRANSFER_COUNT.value_counts().sort_index().items()},
            "intermediary_count_distribution": {str(int(k)): int(v) for k, v in
                table.INTERMEDIARY_COUNT.value_counts().sort_index().items()},
            "same_endpoint_asset_with_conversion": int((table.IS_CONVERSION &
                table.SOURCE_ASSET.eq(table.DESTINATION_ASSET)).sum()),
            "most_common_asset_pairs": pairs.head(10).to_dict("records"),
            "most_common_conversion_asset_pairs": conversion_pairs.head(10).to_dict("records")}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_table_once(table: pa.Table, path: Path) -> None:
    """Preserve an existing artifact unless its schema and values are identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(pq.read_table(path).equals(table), f"Existing artifact differs: {path}; choose a new --run-name")
    else:
        pq.write_table(table, path)
    require(pq.read_table(path).equals(table), f"Parquet serialization mismatch: {path}")


def process_split(name: str, directory: Path, run_name: str) -> dict:
    """Reconstruct, verify against the supplied helper and persist both tables."""
    input_paths = [directory / n for n in ("transactions.parquet", "transfers.parquet", "market_rates.csv")]
    fingerprints = {str(p.relative_to(REPO_ROOT)): sha256(p) for p in input_paths}
    original_tx = pq.read_table(input_paths[0])
    original_legs = pq.read_table(input_paths[1])
    tx = original_tx.to_pandas()
    legs = original_legs.to_pandas()
    rates = pd.read_csv(input_paths[2])
    result = prepare_transactions(tx, legs, rates)
    spec = importlib.util.spec_from_file_location("supplied_payment_reference", REPO_ROOT / "data/traning_data/payments.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    reference = pd.DataFrame(helper.project(original_tx.to_pylist(), helper.load_rates(directory)))
    require(reference.TRANSACTION_HASH.tolist() == result.TRANSACTION_HASH.tolist(), "Reference alignment mismatch")
    require(np.allclose(result.DESTINATION_AMOUNT_USD, reference.VALUE, rtol=1e-12, atol=1e-12),
            "Destination USD differs from supplied helper")
    ordered_legs = original_legs.sort_by([("TRANSACTION_HASH", "ascending"), ("TRANSFER_INDEX", "ascending")])
    transaction_path = output_path(f"{run_name}/{name}/transactions.parquet")
    leg_path = output_path(f"{run_name}/{name}/transfer_legs.parquet")
    write_table_once(pa.Table.from_pandas(result, preserve_index=False), transaction_path)
    write_table_once(ordered_legs, leg_path)
    for path in input_paths:
        require(sha256(path) == fingerprints[str(path.relative_to(REPO_ROOT))], f"Source file changed: {path}")
    details = summarize(result)
    details["paths"] = {"transactions": str(transaction_path.relative_to(REPO_ROOT)),
                        "transfer_legs": str(leg_path.relative_to(REPO_ROOT))}
    details["input_sha256"] = fingerprints
    details["output_sha256"] = {str(p.relative_to(REPO_ROOT)): sha256(p) for p in (transaction_path, leg_path)}
    details["checks"] = {"exact_transaction_coverage_and_order": True, "raw_leg_schema_and_values_preserved": True,
                         "leg_path_and_destination_json_match": True, "value_units_verified": True,
                         "missing_endpoint_rates": 0, "all_destination_usd_match_supplied_helper": True,
                         "input_files_unchanged": True}
    samples = []
    for category, mask in [
        ("direct_xrp", result.TRANSFER_COUNT.eq(1) & result.SOURCE_ASSET.eq("XRP")),
        ("direct_iou", result.TRANSFER_COUNT.eq(1) & result.SOURCE_ASSET.ne("XRP")),
        ("one_conversion_step", result.CONVERSION_STEP_COUNT.eq(1)),
        ("two_conversion_steps", result.CONVERSION_STEP_COUNT.eq(2)),
    ]:
        candidates = result.loc[mask]
        if candidates.empty:
            continue
        row = candidates.iloc[0]
        sample_legs = legs.loc[legs.TRANSACTION_HASH.eq(row.TRANSACTION_HASH)].sort_values("TRANSFER_INDEX")
        sample = json.loads(pd.DataFrame([row]).to_json(orient="records", double_precision=15))[0]
        sample["category"] = category
        sample["asset_sequence"] = ["XRP" if s == "XRP" else f"{a}:{s}"
                                    for a, s in zip(sample_legs.TOKEN_ADDRESS, sample_legs.SYMBOL)]
        hour = int(row.TIMESTAMP) // 3600 * 3600
        for side in ("SOURCE", "DESTINATION"):
            rate = rates.loc[rates.TIMESTAMP.eq(hour) & rates.ASSET.eq(row[f"{side}_ASSET"]), "PRICE_MICRO_USD"].item()
            sample[f"{side}_PRICE_USD"] = int(rate) / SCALE
        sample["reference_hour_utc"] = str(pd.to_datetime(hour, unit="s", utc=True))
        samples.append(sample)
    details["sample_transactions"] = samples
    return details


def markdown_report(report: dict) -> str:
    """Render the requested split-level conversion summary and sample checks."""
    lines = ["# Transaction reconstruction and conversion summary", "",
             f"Command: `{report['command']}`", "",
             "Source and destination amounts use first/last executed legs. VALUE is already normalized; "
             "XRP SOURCE_VALUE is drops. Assets retain issuer identity. USD amounts use separate "
             "endpoint asset prices at the transaction's containing UTC hour. Fees remain separate.", "",
             "Conversion steps count adjacent asset changes, including issuer changes; they do not count "
             "same-asset legs. IS_CONVERSION is steps > 0, even for a path returning to its original asset. "
             "Intermediaries are unique path addresses excluding sender/receiver, not AML layering evidence.", "",
             "| Split | Transactions | With conversion | Actual steps | Without conversion | Conversion % |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, s in report["splits"].items():
        lines.append(f"| {name} | {s['total_transactions']:,} | {s['conversion_transactions']:,} | "
                     f"{s['total_conversion_steps']:,} | {s['non_conversion_transactions']:,} | {s['conversion_percentage']:.4f}% |")
    lines += ["", "| Split | 0 steps | 1 step | 2 steps |", "|---|---:|---:|---:|"]
    for name, s in report["splits"].items():
        d = s["conversion_step_distribution"]
        lines.append(f"| {name} | {d.get('0', 0):,} | {d.get('1', 0):,} | {d.get('2', 0):,} |")
    for name, s in report["splits"].items():
        lines += ["", f"## {name}: ten most common endpoint asset pairs", "",
                  "| Source asset | Destination asset | Transactions |", "|---|---|---:|"]
        for p in s["most_common_asset_pairs"]:
            lines.append(f"| `{p['SOURCE_ASSET']}` | `{p['DESTINATION_ASSET']}` | {p['count']:,} |")
        lines += ["", "Ten most common pairs among conversion transactions only:", "",
                  "| Source asset | Destination asset | Transactions |", "|---|---|---:|"]
        for p in s["most_common_conversion_asset_pairs"]:
            lines.append(f"| `{p['SOURCE_ASSET']}` | `{p['DESTINATION_ASSET']}` | {p['count']:,} |")
        lines += ["", "Sample checks (full hashes, paths, prices and all fields are in the JSON report):", "",
                  "| Sample | Source units × USD price | Source USD | Destination units × USD price | Destination USD | Steps |",
                  "|---|---|---:|---|---:|---:|"]
        for x in s["sample_transactions"]:
            lines.append(f"| {x['category']} | {x['SOURCE_AMOUNT']:.6f} × {x['SOURCE_PRICE_USD']:.6f} | "
                         f"{x['SOURCE_AMOUNT_USD']:.8f} | {x['DESTINATION_AMOUNT']:.6f} × "
                         f"{x['DESTINATION_PRICE_USD']:.6f} | {x['DESTINATION_AMOUNT_USD']:.8f} | {x['CONVERSION_STEP_COUNT']} |")
    lines += ["", "All transaction joins, contiguous leg indices, path endpoints, delivered JSON, units, fees, "
              "hourly endpoint rates, source-file hashes and Parquet round-trips passed. Destination USD "
              "matches the supplied payment helper for every transaction in every split. Sorted raw legs "
              "retain every original column/value/type. Labels and annotation metadata were not read.", "",
              "The current data happens to change assets at every adjacent leg, so steps = legs − 1 here. "
              "Tests also cover same-asset extra legs and return-to-source-asset paths to avoid making that assumption.", "",
              f"Generated tables are under feature_workspace/generated/{report['run_name']}/{{train,validation,test}}/. "
              "Original datasets and the measured baseline are preserved. No model was trained in this step."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="transaction_tables_v1")
    args = parser.parse_args()
    require(bool(args.run_name) and Path(args.run_name).name == args.run_name and args.run_name not in (".", ".."),
            "Run name must be a single directory name")
    command = [".venv/bin/python", "-m", "feature_workspace.prepare_transactions"]
    if args.run_name != "transaction_tables_v1":
        command += ["--run-name", args.run_name]
    report = {"command": shlex.join(command),
              "run_name": args.run_name, "columns": COLUMNS,
              "versions": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "pyarrow")},
              "code_sha256": sha256(Path(__file__)), "splits": {}}
    for name, directory in SPLITS.items():
        report["splits"][name] = process_split(name, directory, args.run_name)
        print(name, json.dumps({k: v for k, v in report["splits"][name].items()
                              if k in ("total_transactions", "conversion_transactions", "total_conversion_steps",
                                       "non_conversion_transactions", "conversion_step_distribution", "conversion_percentage")}))
    # Keep full artifacts isolated, and publish only aggregate summaries/sample checks.
    summary = output_path(f"{args.run_name}/summary.json")
    summary.write_text(json.dumps(report, indent=2) + "\n")
    report_dir = REPO_ROOT / "reports"
    (report_dir / "transaction_preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    (report_dir / "transaction_preparation.md").write_text(markdown_report(report))


if __name__ == "__main__":
    main()
