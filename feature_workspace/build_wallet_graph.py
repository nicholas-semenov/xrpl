"""Build separate directed wallet multigraphs as lossless chronological edge lists.

Run: .venv/bin/python -m feature_workspace.build_wallet_graph
No labels, raw conversion legs, pattern identifiers or estimators are used.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import importlib.metadata
import json
from pathlib import Path
import platform
import shlex

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from feature_workspace.paths import REPO_ROOT, output_path
from feature_workspace.prepare_transactions import (COLUMNS, SPLITS, integer_values, require,
                                                     sha256, write_table_once)

EDGE_ORDER = ["TIMESTAMP", "TRANSACTION_HASH"]
INPUT_RUN = "transaction_tables_v1"


@dataclass
class WalletGraph:
    """One split's payment events and wallet table, with chronological adjacency.

    Edge IDs are hashes, not wallet pairs. Treat nodes/edges as immutable; query
    methods return copies. No time-respecting path or AML detector is implemented.
    """
    split: str
    edges: pd.DataFrame
    nodes: pd.DataFrame
    _outgoing: dict = field(init=False, repr=False)
    _incoming: dict = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._outgoing = self.edges.groupby("SENDER", sort=False).indices
        self._incoming = self.edges.groupby("RECEIVER", sort=False).indices

    def _query(self, index: dict, wallet: str, after: int | None, through: int | None) -> pd.DataFrame:
        result = self.edges.iloc[index.get(wallet, np.array([], dtype="int64"))]
        if after is not None:
            result = result.loc[result.TIMESTAMP.gt(after)]
        if through is not None:
            result = result.loc[result.TIMESTAMP.le(through)]
        return result.copy()

    def outgoing(self, wallet: str, *, after: int | None = None,
                 through: int | None = None) -> pd.DataFrame:
        """Outgoing events ordered by time/hash in the interval (after, through]."""
        return self._query(self._outgoing, wallet, after, through)

    def incoming(self, wallet: str, *, after: int | None = None,
                 through: int | None = None) -> pd.DataFrame:
        """Incoming events ordered by time/hash in the interval (after, through]."""
        return self._query(self._incoming, wallet, after, through)


def build_wallet_graph(transactions: pd.DataFrame, split: str) -> WalletGraph:
    """Preserve one directed edge per canonical transaction, including parallel edges.

    Only the 15 canonical columns are selected; additional annotations cannot
    influence the graph. No internal-leg or intermediary expansion is performed.
    """
    require(isinstance(split, str) and bool(split), "A split identity is required")
    require(set(COLUMNS).issubset(transactions.columns), "Missing canonical transaction columns")
    edges = transactions.loc[:, COLUMNS].copy()
    require(len(edges) > 0, "Cannot build an empty payment graph")
    for col in ["TRANSACTION_HASH", "SENDER", "RECEIVER", "SOURCE_ASSET", "DESTINATION_ASSET"]:
        require(edges[col].map(lambda x: isinstance(x, str) and bool(x)).all(), f"Invalid {col}")
    require(edges.TRANSACTION_HASH.is_unique, "Duplicate transaction edge ID")
    require(edges.notna().all().all(), "Missing edge attributes")
    timestamp = integer_values(edges.TIMESTAMP, "timestamp")
    require(timestamp.eq(edges.TIMESTAMP).all(), "Changed timestamp")
    for col in ["TRANSFER_COUNT", "CONVERSION_STEP_COUNT", "INTERMEDIARY_COUNT"]:
        integer_values(edges[col], col)
    require(pd.api.types.is_bool_dtype(edges.IS_CONVERSION), "IS_CONVERSION must be boolean")
    require(edges.IS_CONVERSION.eq(edges.CONVERSION_STEP_COUNT.gt(0)).all(), "Inconsistent conversion flag")
    require(edges.CONVERSION_STEP_COUNT.ge(0).all() and
            edges.CONVERSION_STEP_COUNT.lt(edges.TRANSFER_COUNT).all(), "Invalid conversion steps")
    require(edges.INTERMEDIARY_COUNT.ge(0).all(), "Negative intermediary count")
    for col in ["SOURCE_AMOUNT", "DESTINATION_AMOUNT", "SOURCE_AMOUNT_USD", "DESTINATION_AMOUNT_USD", "FEE_XRP"]:
        require(pd.api.types.is_numeric_dtype(edges[col]) and np.isfinite(edges[col]).all(), f"Invalid {col}")
        require(edges[col].ge(0).all() if col == "FEE_XRP" else edges[col].gt(0).all(), f"Invalid {col} sign")
    # Keep original integer/float values and types; sorting is the only edge change.
    edges = edges.sort_values(EDGE_ORDER, kind="stable").reset_index(drop=True)
    require(edges.set_index("TRANSACTION_HASH").sort_index().equals(
        transactions.loc[:, COLUMNS].set_index("TRANSACTION_HASH").sort_index()),
        "Prepared edge attributes or transaction coverage changed")
    wallets = pd.Index(sorted(set(edges.SENDER) | set(edges.RECEIVER)), name="WALLET")
    nodes = pd.DataFrame(index=wallets)
    incoming, outgoing = edges.groupby("RECEIVER"), edges.groupby("SENDER")
    nodes["IN_DEGREE"] = incoming.size().reindex(wallets, fill_value=0).astype("int64")
    nodes["OUT_DEGREE"] = outgoing.size().reindex(wallets, fill_value=0).astype("int64")
    nodes["TOTAL_DEGREE"] = nodes.IN_DEGREE + nodes.OUT_DEGREE
    nodes["UNIQUE_IN_NEIGHBORS"] = incoming.SENDER.nunique().reindex(wallets, fill_value=0).astype("int64")
    nodes["UNIQUE_OUT_NEIGHBORS"] = outgoing.RECEIVER.nunique().reindex(wallets, fill_value=0).astype("int64")
    nodes["INCOMING_USD"] = incoming.DESTINATION_AMOUNT_USD.sum().reindex(wallets, fill_value=0.)
    nodes["OUTGOING_USD"] = outgoing.SOURCE_AMOUNT_USD.sum().reindex(wallets, fill_value=0.)
    source_events = edges[["TRANSACTION_HASH", "TIMESTAMP", "SENDER"]].rename(columns={"SENDER": "WALLET"})
    destination_events = edges[["TRANSACTION_HASH", "TIMESTAMP", "RECEIVER"]].rename(columns={"RECEIVER": "WALLET"})
    incident = pd.concat([source_events, destination_events]).drop_duplicates(["WALLET", "TRANSACTION_HASH"])
    by_wallet = incident.groupby("WALLET")
    nodes["TRANSACTION_COUNT"] = by_wallet.size().reindex(wallets).astype("int64")
    nodes["FIRST_TIMESTAMP"] = by_wallet.TIMESTAMP.min().reindex(wallets)
    nodes["LAST_TIMESTAMP"] = by_wallet.TIMESTAMP.max().reindex(wallets)
    require(int(nodes.IN_DEGREE.sum()) == len(edges) == int(nodes.OUT_DEGREE.sum()), "Degree/edge mismatch")
    loops = int(edges.SENDER.eq(edges.RECEIVER).sum())
    require(int(nodes.TRANSACTION_COUNT.sum()) == 2 * len(edges) - loops, "Incident count mismatch")
    for node_column, edge_column in [("INCOMING_USD", "DESTINATION_AMOUNT_USD"), ("OUTGOING_USD", "SOURCE_AMOUNT_USD")]:
        require(np.isclose(nodes[node_column].sum(), edges[edge_column].sum(), rtol=1e-12, atol=1e-8),
                f"Volume aggregation mismatch: {node_column}")
    return WalletGraph(split, edges, nodes.reset_index())


def assert_split_separation(graphs: dict[str, WalletGraph]) -> dict:
    """Fail if supplied disjoint synthetic worlds share hashes or wallet addresses."""
    result = {}
    names = list(graphs)
    for i, a in enumerate(names):
        require(graphs[a].split == a, "Graph/split identity mismatch")
        for b in names[i + 1:]:
            hashes = set(graphs[a].edges.TRANSACTION_HASH) & set(graphs[b].edges.TRANSACTION_HASH)
            wallets = set(graphs[a].nodes.WALLET) & set(graphs[b].nodes.WALLET)
            require(not hashes and not wallets, f"Mixed split identities between {a} and {b}")
            result[f"{a}/{b}"] = {"shared_transaction_hashes": len(hashes), "shared_wallets": len(wallets)}
    return result


def numeric_summary(values: pd.Series) -> dict:
    result = values.describe(percentiles=[.25, .5, .75, .95, .99]).to_dict()
    result["std"] = values.std(ddof=0)
    return {str(k): float(v) for k, v in result.items()}


def summarize_graph(graph: WalletGraph) -> dict:
    """Report multigraph edge degrees separately from distinct counterparties."""
    nodes, edges = graph.nodes, graph.edges
    pairs = edges.groupby(["SENDER", "RECEIVER"]).size()
    count_columns = ["IN_DEGREE", "OUT_DEGREE", "UNIQUE_IN_NEIGHBORS", "UNIQUE_OUT_NEIGHBORS", "TRANSACTION_COUNT"]
    bins = [-1, 0, 1, 5, 10, 25, 50, 100, 250, 500, np.inf]
    labels = ["0", "1", "2-5", "6-10", "11-25", "26-50", "51-100", "101-250", "251-500", "501+"]
    histogram = pd.cut(nodes.TRANSACTION_COUNT, bins=bins, labels=labels).value_counts(sort=False)
    out_usd, in_usd = float(edges.SOURCE_AMOUNT_USD.sum()), float(edges.DESTINATION_AMOUNT_USD.sum())
    return {
        "wallet_nodes": len(nodes), "transaction_edges": len(edges),
        "unique_senders": int(edges.SENDER.nunique()), "unique_receivers": int(edges.RECEIVER.nunique()),
        "unique_directed_wallet_pairs": len(pairs),
        "wallets_with_incoming_and_outgoing": int((nodes.IN_DEGREE.gt(0) & nodes.OUT_DEGREE.gt(0)).sum()),
        "wallets_with_incoming_only": int((nodes.IN_DEGREE.gt(0) & nodes.OUT_DEGREE.eq(0)).sum()),
        "wallets_with_outgoing_only": int((nodes.OUT_DEGREE.gt(0) & nodes.IN_DEGREE.eq(0)).sum()),
        "self_loop_edges": int(edges.SENDER.eq(edges.RECEIVER).sum()),
        "pairs_with_multiple_edges": int(pairs.gt(1).sum()), "extra_parallel_edges": len(edges) - len(pairs),
        "max_transactions_per_directed_pair": int(pairs.max()),
        "total_incoming_usd": in_usd, "total_outgoing_usd": out_usd,
        "source_minus_destination_usd": out_usd - in_usd,
        "statistics": {c: numeric_summary(nodes[c]) for c in count_columns},
        "exact_count_distributions": {c: {str(int(k)): int(v) for k, v in nodes[c].value_counts().sort_index().items()}
                                      for c in count_columns},
        "incident_transaction_count_bins": {str(k): int(v) for k, v in histogram.items()},
        "first_transaction_utc": str(pd.to_datetime(edges.TIMESTAMP.min(), unit="s", utc=True)),
        "last_transaction_utc": str(pd.to_datetime(edges.TIMESTAMP.max(), unit="s", utc=True)),
        "edges_with_shared_timestamp": int(edges.TIMESTAMP.duplicated(keep=False).sum()),
    }


def load_wallet_graph(directory: Path, expected_split: str) -> WalletGraph:
    """Verify artifact hashes and reconstruct adjacency deterministically from edges."""
    manifest = json.loads((directory / "manifest.json").read_text())
    require(manifest["split"] == expected_split, "Saved graph belongs to another split")
    for filename in ("edges.parquet", "nodes.parquet"):
        require(sha256(directory / filename) == manifest["artifact_sha256"][filename], f"Corrupt graph artifact: {filename}")
    edges = pd.read_parquet(directory / "edges.parquet")
    nodes = pd.read_parquet(directory / "nodes.parquet")
    graph = build_wallet_graph(edges, expected_split)
    require(graph.edges.equals(edges), "Saved edge order/attributes differ on reconstruction")
    require(graph.nodes.equals(nodes), "Saved wallet statistics differ on reconstruction")
    require(len(edges) == manifest["transaction_edges"] and len(nodes) == manifest["wallet_nodes"], "Manifest counts differ")
    return graph


def validate_against_original(graph: WalletGraph, original_path: Path) -> None:
    """Independently check original transaction coverage, direction and timestamp."""
    raw = pd.read_parquet(original_path, columns=["TRANSACTION_HASH", "TIMESTAMP", "ACCOUNT", "EXTRA_TRANSACTION_FIELDS"])
    require(raw.TRANSACTION_HASH.is_unique and len(raw) == len(graph.edges) and
            set(raw.TRANSACTION_HASH) == set(graph.edges.TRANSACTION_HASH), "Original transaction coverage mismatch")
    aligned = graph.edges.set_index("TRANSACTION_HASH").loc[raw.TRANSACTION_HASH]
    require(aligned.SENDER.tolist() == raw.ACCOUNT.tolist(), "Original sender direction mismatch")
    require(aligned.RECEIVER.tolist() == raw.EXTRA_TRANSACTION_FIELDS.map(lambda x: json.loads(x)["Destination"]).tolist(),
            "Original receiver direction mismatch")
    require(aligned.TIMESTAMP.tolist() == raw.TIMESTAMP.tolist(), "Original transaction timestamps changed")


def markdown_report(report: dict) -> str:
    lines = ["# Wallet transaction graphs", "", f"Command: `{report['command']}`", "",
             "Three separate directed multigraphs; node = wallet, edge/key = transaction hash, "
             "direction = SENDER → RECEIVER. All 15 prepared columns are retained without aggregation "
             "or numeric conversion. Full seven-day histories are used. No labels, conversion legs, "
             "AML pattern IDs or model fitting are involved.", "",
             "| Split | Nodes | Edges | Senders | Receivers | Directed pairs | Both directions | Incoming only |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, s in report["splits"].items():
        lines.append(f"| {name} | {s['wallet_nodes']:,} | {s['transaction_edges']:,} | {s['unique_senders']:,} | "
                     f"{s['unique_receivers']:,} | {s['unique_directed_wallet_pairs']:,} | "
                     f"{s['wallets_with_incoming_and_outgoing']:,} | {s['wallets_with_incoming_only']:,} |")
    lines += ["", "| Split | Incoming USD (delivered) | Outgoing USD (spent) | Extra parallel edges | Self-loops |",
              "|---|---:|---:|---:|---:|"]
    for name, s in report["splits"].items():
        lines.append(f"| {name} | {s['total_incoming_usd']:,.6f} | {s['total_outgoing_usd']:,.6f} | "
                     f"{s['extra_parallel_edges']:,} | {s['self_loop_edges']:,} |")
    lines += ["", "Incoming volume uses DESTINATION_AMOUNT_USD; outgoing uses SOURCE_AMOUNT_USD. "
              "These valuations differ for conversions because of reference prices and executed quotes/spreads. "
              "Network fees remain a separate XRP attribute; no fee edges or leg-value sums are added.", "",
              "IN_DEGREE/OUT_DEGREE count transaction edges, including repeated wallet pairs. "
              "UNIQUE_IN_NEIGHBORS/UNIQUE_OUT_NEIGHBORS count distinct counterparties. TRANSACTION_COUNT "
              "counts distinct incident transactions; a self-loop counts once here and once in each directional degree. "
              "Statistics include zero-degree wallets; standard deviations are population values.", ""]
    for name, s in report["splits"].items():
        lines += ["", f"## {name}", "", f"Observed events: {s['first_transaction_utc']} through {s['last_transaction_utc']}.", "",
                  "| Statistic | Min | Mean | Median | 95th percentile | Max |", "|---|---:|---:|---:|---:|---:|"]
        for column, values in s["statistics"].items():
            lines.append(f"| {column} | {values['min']:.0f} | {values['mean']:.4f} | {values['50%']:.1f} | "
                         f"{values['95%']:.2f} | {values['max']:.0f} |")
        lines += ["", "| Incident transactions per wallet | Wallets |", "|---|---:|"]
        for bucket, count in s["incident_transaction_count_bins"].items():
            lines.append(f"| {bucket} | {count} |")
    lines += ["", "Exact degree/count histograms, full precision volumes, checks and artifact hashes are in "
              "wallet_graphs.json. Per-wallet statistics are stored in nodes.parquet. Raw and prepared inputs "
              "remain unchanged. Original hashes/directions/timestamps and every prepared edge attribute were checked.", "",
              "Edges are sorted by (TIMESTAMP, TRANSACTION_HASH); this order is also used by incoming/outgoing "
              "adjacency queries. Hash ordering only resolves timestamp ties deterministically, not causally. "
              "For a strictly later hop use outgoing(wallet, after=previous_timestamp). No path detector is implemented.", "",
              "Cross-split wallet/hash intersections are zero. All graph artifacts were reloaded and rebuilt identically. "
              "No integrity issues were discovered. Incoming-only wallets and parallel payments are retained."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="wallet_graphs_v1")
    args = parser.parse_args()
    require(bool(args.run_name) and Path(args.run_name).name == args.run_name and args.run_name not in (".", "..", INPUT_RUN),
            "Choose a distinct single-directory graph run name")
    inputs = {name: output_path(f"{INPUT_RUN}/{name}/transactions.parquet") for name in SPLITS}
    raw_paths = {name: path / "transactions.parquet" for name, path in SPLITS.items()}
    # Fingerprint every previous preparation artifact, including detailed legs and summary.
    preserved_paths = sorted((output_path(INPUT_RUN)).rglob("*.parquet")) + [output_path(f"{INPUT_RUN}/summary.json")]
    preserved_paths += list(raw_paths.values())
    before = {str(p.relative_to(REPO_ROOT)): sha256(p) for p in preserved_paths}
    graphs = {name: build_wallet_graph(pd.read_parquet(path), name) for name, path in inputs.items()}
    separation = assert_split_separation(graphs)
    command = [".venv/bin/python", "-m", "feature_workspace.build_wallet_graph"]
    if args.run_name != "wallet_graphs_v1":
        command += ["--run-name", args.run_name]
    report = {"command": shlex.join(command), "run_name": args.run_name, "input_run": INPUT_RUN,
              "graph_type": "directed_multigraph", "node_key": "WALLET", "edge_key": "TRANSACTION_HASH",
              "edge_attributes": COLUMNS, "edge_order": EDGE_ORDER, "cross_split_overlaps": separation,
              "python": platform.python_version(),
              "versions": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "pyarrow")},
              "source_sha256": {str(p.relative_to(REPO_ROOT)): sha256(p) for p in
                  [Path(__file__), REPO_ROOT / "feature_workspace/prepare_transactions.py",
                   REPO_ROOT / "feature_workspace/paths.py", REPO_ROOT / "requirements-baseline.txt"]},
              "preserved_input_sha256": before, "splits": {}}
    for name, graph in graphs.items():
        validate_against_original(graph, raw_paths[name])
        # Independently rebuild after input shuffling: both tables must be identical.
        repeat = build_wallet_graph(pd.read_parquet(inputs[name]).sample(frac=1, random_state=0), name)
        require(graph.edges.equals(repeat.edges) and graph.nodes.equals(repeat.nodes), "Nondeterministic graph")
        files = {n: output_path(f"{args.run_name}/{name}/{n}") for n in ["edges.parquet", "nodes.parquet", "manifest.json"]}
        for filename, frame in [("edges.parquet", graph.edges), ("nodes.parquet", graph.nodes)]:
            write_table_once(pa.Table.from_pandas(frame, preserve_index=False), files[filename])
        manifest = {"split": name, "graph_type": "directed_multigraph", "edge_key": "TRANSACTION_HASH",
                    "edge_order": EDGE_ORDER, "wallet_nodes": len(graph.nodes), "transaction_edges": len(graph.edges),
                    "prepared_input_sha256": before[str(inputs[name].relative_to(REPO_ROOT))],
                    "artifact_sha256": {n: sha256(files[n]) for n in ("edges.parquet", "nodes.parquet")}}
        if files["manifest.json"].exists():
            require(json.loads(files["manifest.json"].read_text()) == manifest, "Existing graph manifest differs; use a new --run-name")
        else:
            files["manifest.json"].write_text(json.dumps(manifest, indent=2) + "\n")
        restored = load_wallet_graph(files["manifest.json"].parent, name)
        require(restored.edges.equals(graph.edges) and restored.nodes.equals(graph.nodes), "Graph round-trip mismatch")
        s = summarize_graph(graph)
        s["files"] = {k: str(p.relative_to(REPO_ROOT)) for k, p in files.items()}
        s["artifact_sha256"] = {k: sha256(p) for k, p in files.items()}
        s["checks"] = {"unique_transaction_edge_ids": True, "exact_prepared_edge_attributes": True,
                       "original_coverage_direction_timestamps": True, "conversion_legs_not_expanded": True,
                       "chronological_edges_and_adjacency": True, "deterministic_after_input_shuffle": True,
                       "lossless_artifact_reconstruction": True}
        report["splits"][name] = s
        print(name, json.dumps({k: s[k] for k in ["wallet_nodes", "transaction_edges", "unique_senders", "unique_receivers",
                                                "unique_directed_wallet_pairs", "wallets_with_incoming_and_outgoing",
                                                "total_incoming_usd", "total_outgoing_usd"]}))
    require(all(sha256(REPO_ROOT / p) == digest for p, digest in before.items()), "An input artifact was modified")
    report["preserved_inputs_unchanged"] = True
    output_path(f"{args.run_name}/summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPO_ROOT / "reports/wallet_graphs.json").write_text(json.dumps(report, indent=2) + "\n")
    (REPO_ROOT / "reports/wallet_graphs.md").write_text(markdown_report(report))


if __name__ == "__main__":
    main()
