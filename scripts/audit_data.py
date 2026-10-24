"""Audit supplied XRPL data without fitting a model or changing source files."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/traning_data"
SPLITS = {"train": PACKAGE / "train", "validation": PACKAGE / "validation",
          "test": ROOT / "data/test_data"}
spec = importlib.util.spec_from_file_location("payments", PACKAGE / "payments.py")
payments = importlib.util.module_from_spec(spec)
spec.loader.exec_module(payments)


def summary(series: pd.Series) -> dict:
    """Return compact numeric quantiles with standard JSON-compatible values."""
    return {str(k): float(v) for k, v in series.astype(float).describe(
        percentiles=[0.01, 0.5, 0.95, 0.99]).items()}


def audit_split(path: Path) -> tuple[dict, set, set]:
    """Validate joins, units, rates and the bundled payment projection."""
    tables = {name: pd.read_parquet(path / f"{name}.parquet")
              for name in ("transactions", "transfers", "blocks")}
    tx, legs, blocks = (tables[n] for n in ("transactions", "transfers", "blocks"))
    rates = pd.read_csv(path / "market_rates.csv")
    result = {"path": str(path.relative_to(ROOT)), "tables": {}}
    for name, table in tables.items():
        result["tables"][name] = {
            "rows": len(table), "columns": len(table.columns),
            "schema": {f.name: str(f.type) for f in pq.read_schema(path / f"{name}.parquet")},
            "missing": {c: int(table[c].isna().sum()) for c in table},
            "distinct": {c: int(table[c].nunique()) for c in table},
        }
    hashes = set(tx.TRANSACTION_HASH)
    assert tx.TRANSACTION_HASH.notna().all() and tx.TRANSACTION_HASH.is_unique
    assert set(legs.TRANSACTION_HASH) == hashes
    assert not legs.duplicated(["TRANSACTION_HASH", "TRANSFER_INDEX"]).any()
    block_keys = ["LEDGER_INDEX", "LEDGER_HASH"]
    assert not blocks.duplicated(block_keys).any()
    for table in (tx, legs):
        joined = table.merge(blocks[block_keys + ["TIMESTAMP"]], on=block_keys,
                             how="left", validate="many_to_one", suffixes=("", "_block"))
        assert joined.TIMESTAMP_block.notna().all()
        assert joined.TIMESTAMP.eq(joined.TIMESTAMP_block).all()
        assert pd.to_datetime(table.TIMESTAMP.astype("int64"), unit="s", utc=True).eq(table.DATETIME).all()
    matched = legs.merge(tx[["TRANSACTION_HASH", "TIMESTAMP", *block_keys, "TRANSACTION_INDEX"]],
                         on="TRANSACTION_HASH", validate="many_to_one", suffixes=("", "_tx"))
    for col in ["TIMESTAMP", *block_keys, "TRANSACTION_INDEX"]:
        assert matched[col].eq(matched[col + "_tx"]).all()
    ordered = legs.sort_values(["TRANSACTION_HASH", "TRANSFER_INDEX"])
    counts = ordered.groupby("TRANSACTION_HASH").size()
    assert counts.between(1, 3).all()
    assert ordered.TRANSFER_INDEX.astype(int).eq(ordered.groupby("TRANSACTION_HASH").cumcount()).all()
    first = ordered.groupby("TRANSACTION_HASH").head(1).set_index("TRANSACTION_HASH").loc[tx.TRANSACTION_HASH]
    last = ordered.groupby("TRANSACTION_HASH").tail(1).set_index("TRANSACTION_HASH").loc[tx.TRANSACTION_HASH]
    fields = tx.EXTRA_TRANSACTION_FIELDS.map(json.loads)
    delivered = tx.DELIVERED_AMOUNT.map(json.loads)
    destinations = fields.map(lambda x: x["Destination"])
    assert first.FROM_ADDRESS.to_numpy().tolist() == tx.ACCOUNT.tolist()
    assert last.TO_ADDRESS.to_numpy().tolist() == destinations.tolist()
    native = legs.SYMBOL.eq("XRP")
    assert legs.loc[native, "TOKEN_ADDRESS"].eq(payments.XRP).all()
    assert np.allclose(legs.loc[native, "SOURCE_VALUE"] / 1e6, legs.loc[native, "VALUE"], rtol=1e-12, atol=1e-12)
    assert np.allclose(legs.loc[~native, "SOURCE_VALUE"], legs.loc[~native, "VALUE"], rtol=1e-12, atol=1e-12)
    assert np.isfinite(legs.VALUE).all() and legs.VALUE.gt(0).all()
    assert np.allclose(tx.SOURCE_FEE.astype(float) / 1e6, tx.FEE, rtol=1e-12, atol=1e-12)
    decoded = [payments.decode_amount(x) for x in delivered]
    delivered_assets = [a for a, _ in decoded]
    expected_assets = np.where(last.SYMBOL.eq("XRP"), "XRP", last.TOKEN_ADDRESS + ":" + last.SYMBOL)
    assert list(expected_assets) == delivered_assets
    assert np.allclose(last.VALUE.to_numpy(), [u / 1e6 for _, u in decoded], rtol=1e-12, atol=1e-12)
    legs = legs.assign(ASSET=np.where(native, "XRP", legs.TOKEN_ADDRESS + ":" + legs.SYMBOL),
                       HOUR=legs.TIMESTAMP.astype("int64") // 3600 * 3600)
    assert not rates.duplicated(["TIMESTAMP", "ASSET"]).any()
    assert rates.PRICE_MICRO_USD.gt(0).all()
    priced = legs.merge(rates, left_on=["HOUR", "ASSET"], right_on=["TIMESTAMP", "ASSET"],
                        how="left", validate="many_to_one")
    missing_rates = int(priced.PRICE_MICRO_USD.isna().sum())
    assert missing_rates == 0
    projected = pd.DataFrame(payments.load_payments(path))
    assert len(projected) == len(tx) and projected.TRANSACTION_HASH.is_unique
    assert projected.TRANSACTION_HASH.tolist() == tx.TRANSACTION_HASH.tolist()
    assert projected.FROM_ADDRESS.tolist() == tx.ACCOUNT.tolist()
    assert projected.TO_ADDRESS.tolist() == destinations.tolist()
    assert np.isfinite(projected.VALUE).all() and projected.VALUE.gt(0).all()
    rate_lookup = payments.load_rates(path)
    expected_usd = (last.VALUE.to_numpy() * [payments.price(rate_lookup, int(t), a) / 1e6
                    for t, a in zip(tx.TIMESTAMP, delivered_assets)])
    assert np.allclose(projected.VALUE, expected_usd, rtol=1e-12, atol=1e-12)
    result.update({
        "transaction_time_utc": [str(tx.DATETIME.min()), str(tx.DATETIME.max())],
        "block_time_utc": [str(blocks.DATETIME.min()), str(blocks.DATETIME.max())],
        "transaction_types": tx.TRANSACTION_TYPE.value_counts().to_dict(),
        "transaction_results": tx.TRANSACTION_RESULT.value_counts().to_dict(),
        "success": tx.SUCCESS.value_counts().to_dict(),
        "leg_counts_per_transaction": counts.value_counts().sort_index().to_dict(),
        "transfer_types": legs.TRANSFER_TYPE.value_counts().to_dict(),
        "asset_leg_counts": legs.ASSET.value_counts().to_dict(),
        "customer_wallets": len(set(tx.ACCOUNT) | set(destinations)),
        "all_transfer_wallets": len(set(legs.FROM_ADDRESS) | set(legs.TO_ADDRESS)),
        "rates": {"rows": len(rates), "assets": int(rates.ASSET.nunique()),
                  "hours": int(rates.TIMESTAMP.nunique()), "missing_leg_prices": missing_rates},
        "fee_drops_counts": tx.SOURCE_FEE.astype(int).value_counts().sort_index().to_dict(),
        "json_field_key_sets": fields.map(lambda x: ",".join(sorted(x))).value_counts().to_dict(),
        "delivered_json_types": delivered.map(lambda x: type(x).__name__).value_counts().to_dict(),
        "payment_usd": summary(projected.VALUE),
        "checks": "All asserted integrity, timestamp, endpoint, amount-unit, rate and projection checks passed.",
    })
    if (path / "labels.csv").exists():
        labels = pd.read_csv(path / "labels.csv")
        assert labels.TRANSACTION_HASH.notna().all() and labels.TRANSACTION_HASH.is_unique
        assert set(labels.TRANSACTION_HASH) == hashes
        assert labels.is_suspicious.isin([0, 1]).all()
        joined = projected.merge(labels, on="TRANSACTION_HASH", validate="one_to_one")
        result["labels"] = {
            "rows": len(labels), "columns": labels.columns.tolist(),
            "missing": labels.isna().sum().to_dict(),
            "class_counts": labels.is_suspicious.value_counts().to_dict(),
            "positive_fraction": float(labels.is_suspicious.mean()),
            "difficulty_by_label": pd.crosstab(labels.difficulty, labels.is_suspicious).to_dict(),
            "family_by_label": pd.crosstab(labels.family, labels.is_suspicious).to_dict(),
            "unique_scenarios": int(labels.scenario_id.nunique()),
            "unique_cohorts": int(labels.cohort_id.nunique()),
            "usd_by_label": {int(y): summary(g.VALUE) for y, g in joined.groupby("is_suspicious")},
        }
    return result, hashes, set(legs.FROM_ADDRESS) | set(legs.TO_ADDRESS) | set(tx.ACCOUNT) | set(destinations)


def main() -> None:
    report = {"command": "python3 scripts/audit_data.py", "versions": {
        "pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pyarrow.__version__}, "splits": {}}
    manifest = json.loads((PACKAGE / "checksums.json").read_text())
    report["checksums"] = {name: hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
                           for name, expected in manifest.items()}
    assert all(report["checksums"].values()), "Training package checksum mismatch"
    sets = {}
    for name, path in SPLITS.items():
        report["splits"][name], hashes, wallets = audit_split(path)
        sets[name] = (hashes, wallets)
    report["overlaps"] = {}
    for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]:
        report["overlaps"][f"{a}/{b}"] = {"transaction_hashes": len(sets[a][0] & sets[b][0]),
                                              "wallets": len(sets[a][1] & sets[b][1])}
        assert not sets[a][0] & sets[b][0] and not sets[a][1] & sets[b][1]
    output = ROOT / "reports/data_audit.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    for name, r in report["splits"].items():
        print(name, json.dumps({k: r[k] for k in ["transaction_time_utc", "leg_counts_per_transaction",
                    "customer_wallets", "rates", "payment_usd"]}))
    print("Checksums:", len(manifest), "passed; overlaps:", report["overlaps"])
    print("Saved", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
