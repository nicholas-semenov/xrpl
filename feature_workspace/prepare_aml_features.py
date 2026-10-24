"""Apply identical label-free AML 1–4 logic to the three existing wallet graphs."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shlex
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from feature_workspace.aml_patterns import PATTERNS, WINDOWS, Thresholds, detect_patterns
from feature_workspace.build_wallet_graph import assert_split_separation, load_wallet_graph
from feature_workspace.paths import REPO_ROOT, output_path
from feature_workspace.prepare_transactions import COLUMNS, require, sha256, write_table_once


def feature_table(frame: pd.DataFrame) -> pa.Table:
    """Enforce portable list<int8> motif metadata, including all-empty lists."""
    table = pa.Table.from_pandas(frame, preserve_index=False)
    return table.set_column(table.schema.get_field_index("aml_pattern"), "aml_pattern",
                            pa.array(frame.aml_pattern.tolist(), type=pa.list_(pa.int8())))


def markdown_report(report: dict) -> str:
    lines = ["# AML patterns 1–4: descriptive detections", "", f"Command: `{report['command']}`", "",
             "IDs: 1 fan-in; 2 fan-out; 3 scatter-gather; 4 gather-scatter. Membership is not a suspicion label "
             "or probability. No labels/annotation files were read and no model was trained.", "",
             "| Split | Transactions | ID 1 | ID 2 | ID 3 | ID 4 | Any pattern | Multiple patterns |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, s in report["splits"].items():
        c = s["pattern_transaction_counts"]
        lines.append(f"| {name} | {s['transactions']:,} | {c['1']:,} | {c['2']:,} | {c['3']:,} | {c['4']:,} | "
                     f"{s['transactions_with_any_pattern']:,} | {s['transactions_with_multiple_patterns']:,} |")
    lines += ["", "Counts above are unions across windows; per-pattern counts overlap and must not be summed.", "",
              "| Split | Window | ID 1 | ID 2 | ID 3 | ID 4 |", "|---|---|---:|---:|---:|---:|"]
    for name, s in report["splits"].items():
        for window, c in s["pattern_counts_by_window"].items():
            lines.append(f"| {name} | {window} | {c['1']:,} | {c['2']:,} | {c['3']:,} | {c['4']:,} |")
    lines += ["", f"Each output has {report['output_column_count']} columns: original 15, aml_pattern (list<int8>), "
              f"and {len(report['numeric_feature_columns'])} numerical AML features. Original transaction order, "
              "hash coverage, field values and types were preserved. Parquet artifacts were read back and checked.", "",
              "Default thresholds and exact definitions are in feature_workspace/AML_PATTERNS.md and aml_thresholds.json. "
              "The feature schema separates numeric/categorical model inputs from identifiers and list metadata. "
              "The seven-day motifs are broad structural descriptions and can include legitimate hubs; counts "
              "do not establish detector precision/recall. No performance claim or threshold tuning against targets was made.", "",
              "Strict temporal paths use first timestamp < second timestamp. All witness events fit inside their "
              "specified total window span. USD flow sums deduplicate transaction IDs; two-hop path counts preserve "
              "distinct event pairs. Self-payments remain in output but do not supply motif evidence. Bounds at "
              "the dataset start/end use only observed events and may truncate history.", "",
              "Resource counters, timings, input/output/code hashes, witness counts and window-specific detections "
              "are in aml_patterns.json. Limits fail explicitly without sampling or silent truncation. "
              "All datasets use the same fixed configuration and remain separate."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "feature_workspace/aml_thresholds.json")
    parser.add_argument("--run-name", default="aml_features_v1")
    args = parser.parse_args()
    require(bool(args.run_name) and Path(args.run_name).name == args.run_name and
            args.run_name not in (".", "..", "transaction_tables_v1", "wallet_graphs_v1"), "Invalid output run name")
    cfg = Thresholds(**json.loads(args.config.read_text()))
    cfg.validate()
    graph_root = output_path("wallet_graphs_v1")
    prepared_root = output_path("transaction_tables_v1")
    preserved = sorted(p for root in [graph_root, prepared_root] for p in root.rglob("*")
                       if p.is_file() and p.suffix in (".parquet", ".json"))
    before = {str(p.relative_to(REPO_ROOT)): sha256(p) for p in preserved}
    graphs = {name: load_wallet_graph(graph_root / name, name) for name in ["train", "validation", "test"]}
    separation = assert_split_separation(graphs)
    command = [".venv/bin/python", "-m", "feature_workspace.prepare_aml_features"]
    if args.config.resolve() != REPO_ROOT / "feature_workspace/aml_thresholds.json":
        command += ["--config", str(args.config)]
    if args.run_name != "aml_features_v1":
        command += ["--run-name", args.run_name]
    report = {"command": shlex.join(command), "config": asdict(cfg), "windows_seconds": WINDOWS,
              "config_sha256": sha256(args.config), "run_name": args.run_name,
              "source_sha256": {str(p.relative_to(REPO_ROOT)): sha256(p) for p in [Path(__file__),
                  REPO_ROOT / "feature_workspace/aml_patterns.py", REPO_ROOT / "feature_workspace/build_wallet_graph.py"]},
              "preserved_input_sha256": before, "cross_split_overlaps": separation, "splits": {}}
    schema = None
    for name, graph in graphs.items():
        print(f"Detecting {name}...", flush=True)
        started = time.perf_counter()
        extended, info = detect_patterns(graph, cfg)
        canonical = pd.read_parquet(prepared_root / name / "transactions.parquet")
        extended = extended.set_index("TRANSACTION_HASH").loc[canonical.TRANSACTION_HASH].reset_index()
        require(extended[COLUMNS].equals(canonical[COLUMNS]), "Original data/order changed")
        feature_columns = info.pop("numeric_feature_columns")
        descriptions = info.pop("feature_descriptions")
        current_schema = {"numeric_aml_columns": feature_columns, "descriptions": descriptions,
                          "model_numeric_columns": [c for c in COLUMNS if pd.api.types.is_numeric_dtype(canonical[c])] + feature_columns,
                          "model_categorical_columns": ["SOURCE_ASSET", "DESTINATION_ASSET"],
                          "exclude_from_model": ["TRANSACTION_HASH", "SENDER", "RECEIVER", "aml_pattern"],
                          "missing_delay_sentinel": -1, "aml_pattern_arrow_type": "list<int8>",
                          "feature_availability": "offline, within each separate supplied graph window"}
        require(schema is None or current_schema == schema, "Feature schema differs between splits")
        schema = current_schema
        path = output_path(f"{args.run_name}/{name}/transactions.parquet")
        write_table_once(feature_table(extended), path)
        restored = pq.read_table(path)
        require(restored.equals(feature_table(extended)), "AML feature Parquet round-trip mismatch")
        require(np.isfinite(extended[feature_columns].to_numpy()).all(), "Invalid numerical feature")
        info.update({"transactions": len(extended), "columns": len(extended.columns),
                     "seconds": time.perf_counter() - started, "path": str(path.relative_to(REPO_ROOT)),
                     "output_sha256": sha256(path), "original_15_fields_and_order_preserved": True,
                     "label_free": True, "no_suspicion_classification": True})
        report["splits"][name] = info
        print(name, json.dumps({"counts": info["pattern_transaction_counts"], "seconds": info["seconds"],
                                "resource_counts": info["resource_counts"]}), flush=True)
    require(all(sha256(REPO_ROOT / p) == digest for p, digest in before.items()), "Previous artifacts modified")
    report["preserved_inputs_unchanged"] = True
    report["numeric_feature_columns"] = schema["numeric_aml_columns"]
    report["output_column_count"] = next(iter(report["splits"].values()))["columns"]
    output_path(f"{args.run_name}/feature_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    output_path(f"{args.run_name}/summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPO_ROOT / "reports/aml_patterns.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPO_ROOT / "reports/aml_patterns.md").write_text(markdown_report(report))


if __name__ == "__main__":
    main()
