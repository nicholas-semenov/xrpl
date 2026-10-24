"""Correctness of payment multigraphs, temporal adjacency and lossless artifacts."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from feature_workspace.build_wallet_graph import (assert_split_separation, build_wallet_graph,
                                                   load_wallet_graph, summarize_graph,
                                                   validate_against_original)
from feature_workspace.prepare_transactions import COLUMNS, sha256


def toy_transactions():
    """Toy events include parallel/reverse edges, a conversion, a loop and a sink."""
    records = [
        ("later", 300, "A", "B", 12., 12., 0),
        ("earlier", 100, "A", "B", 10., 9.5, 1),
        ("reverse", 200, "B", "A", 5., 5., 0),
        ("tie", 100, "A", "B", 3., 3., 0),
        ("self", 250, "C", "C", 7., 6.9, 2),
        ("sink", 400, "A", "D", 2., 2., 0),
    ]
    rows = []
    for h, t, sender, receiver, source, destination, steps in records:
        rows.append({"TRANSACTION_HASH": h, "TIMESTAMP": t, "SENDER": sender, "RECEIVER": receiver,
                     "SOURCE_ASSET": "issuer:USD" if steps else "XRP",
                     "DESTINATION_ASSET": "XRP" if steps == 1 else ("issuer:USD" if steps else "XRP"),
                     "SOURCE_AMOUNT": source, "DESTINATION_AMOUNT": destination,
                     "SOURCE_AMOUNT_USD": source, "DESTINATION_AMOUNT_USD": destination,
                     "TRANSFER_COUNT": steps + 1, "IS_CONVERSION": steps > 0,
                     "CONVERSION_STEP_COUNT": steps, "INTERMEDIARY_COUNT": steps, "FEE_XRP": .00001})
    return pd.DataFrame(rows).loc[:, COLUMNS]


class WalletGraphTests(unittest.TestCase):
    def test_exact_edge_attributes_parallel_pairs_and_no_leg_expansion(self):
        source = toy_transactions()
        source.loc[0, "SOURCE_AMOUNT_USD"] = np.nextafter(12., 13.)
        original = source.copy(deep=True)
        graph = build_wallet_graph(source, "train")
        self.assertEqual(len(graph.edges), len(source))
        self.assertTrue(graph.edges.TRANSACTION_HASH.is_unique)
        self.assertEqual(graph.edges.TRANSACTION_HASH.tolist(), ["earlier", "tie", "reverse", "self", "later", "sink"])
        self.assertEqual(graph.outgoing("A").RECEIVER.tolist().count("B"), 3)
        self.assertEqual(graph.outgoing("B").RECEIVER.tolist(), ["A"])
        self.assertEqual(graph.nodes.WALLET.tolist(), ["A", "B", "C", "D"])
        self.assertEqual(graph.edges.loc[graph.edges.TRANSACTION_HASH.eq("self"), "TRANSFER_COUNT"].item(), 3)
        self.assertEqual(len(graph.outgoing("C")), 1)  # Three conversion legs remain one user edge.
        assert_frame_equal(source, original, check_exact=True)
        assert_frame_equal(graph.edges.set_index("TRANSACTION_HASH").sort_index(),
                           original.set_index("TRANSACTION_HASH").sort_index(), check_exact=True)

    def test_hand_calculated_degrees_volumes_incident_counts_and_histograms(self):
        graph = build_wallet_graph(toy_transactions(), "train")
        nodes = graph.nodes.set_index("WALLET")
        self.assertEqual(nodes.IN_DEGREE.to_dict(), {"A": 1, "B": 3, "C": 1, "D": 1})
        self.assertEqual(nodes.OUT_DEGREE.to_dict(), {"A": 4, "B": 1, "C": 1, "D": 0})
        self.assertEqual(nodes.TRANSACTION_COUNT.to_dict(), {"A": 5, "B": 4, "C": 1, "D": 1})
        self.assertEqual(nodes.loc["A", "UNIQUE_OUT_NEIGHBORS"], 2)
        self.assertEqual(nodes.loc["C", "TOTAL_DEGREE"], 2)  # Self-loop counts once per direction.
        self.assertEqual(nodes.loc["C", "TRANSACTION_COUNT"], 1)
        s = summarize_graph(graph)
        for key, expected in {"wallet_nodes": 4, "transaction_edges": 6, "unique_senders": 3,
                              "unique_receivers": 4, "unique_directed_wallet_pairs": 4,
                              "wallets_with_incoming_and_outgoing": 3, "wallets_with_incoming_only": 1,
                              "wallets_with_outgoing_only": 0, "extra_parallel_edges": 2,
                              "pairs_with_multiple_edges": 1, "max_transactions_per_directed_pair": 3,
                              "self_loop_edges": 1}.items():
            self.assertEqual(s[key], expected, key)
        self.assertAlmostEqual(s["total_incoming_usd"], 38.4)
        self.assertAlmostEqual(s["total_outgoing_usd"], 39.)
        self.assertEqual(s["exact_count_distributions"]["TRANSACTION_COUNT"], {"1": 2, "4": 1, "5": 1})
        self.assertEqual(sum(s["incident_transaction_count_bins"].values()), 4)
        self.assertEqual(s["statistics"]["OUT_DEGREE"]["min"], 0.)
        self.assertEqual(s["statistics"]["OUT_DEGREE"]["std"], 1.5)

    def test_chronological_adjacency_uses_strict_lower_time_bound(self):
        graph = build_wallet_graph(toy_transactions(), "train")
        self.assertEqual(graph.outgoing("A", after=100, through=300).TRANSACTION_HASH.tolist(), ["later"])
        self.assertEqual(graph.incoming("B", through=100).TRANSACTION_HASH.tolist(), ["earlier", "tie"])
        self.assertTrue(graph.outgoing("D").empty)
        self.assertEqual(graph.outgoing("unknown").columns.tolist(), COLUMNS)
        query = graph.outgoing("A")
        query.loc[:, "SOURCE_AMOUNT_USD"] = 0.
        self.assertTrue(graph.outgoing("A").SOURCE_AMOUNT_USD.gt(0).all())

    def test_deterministic_under_shuffle_and_annotation_changes(self):
        source = toy_transactions()
        reference = build_wallet_graph(source, "train")
        annotated = source.assign(is_suspicious=1, scenario_id="private", cohort_id="private",
                                  family="private", difficulty="hard")
        for seed in [0, 9]:
            other = build_wallet_graph(annotated.sample(frac=1, random_state=seed), "train")
            assert_frame_equal(other.edges, reference.edges, check_exact=True)
            assert_frame_equal(other.nodes, reference.nodes, check_exact=True)

    def test_invalid_or_missing_edge_attributes_fail(self):
        source = toy_transactions()
        cases = []
        cases.append((pd.concat([source, source.iloc[:1]]), "Duplicate transaction"))
        cases.append((source.drop(columns="RECEIVER"), "Missing canonical"))
        bad = source.copy(); bad.loc[0, "SENDER"] = ""
        cases.append((bad, "Invalid SENDER"))
        bad = source.copy(); bad.loc[0, "DESTINATION_AMOUNT_USD"] = np.nan
        cases.append((bad, "Missing edge attributes"))
        bad = source.copy(); bad.loc[0, "SOURCE_AMOUNT_USD"] = np.inf
        cases.append((bad, "Invalid SOURCE_AMOUNT_USD"))
        bad = source.copy(); bad["TIMESTAMP"] = bad.TIMESTAMP.astype(float); bad.loc[0, "TIMESTAMP"] = 300.5
        cases.append((bad, "Non-integral timestamp"))
        bad = source.copy(); bad.loc[0, "IS_CONVERSION"] = True
        cases.append((bad, "Inconsistent conversion flag"))
        for frame, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                build_wallet_graph(frame, "train")

    def test_cross_split_wallet_or_hash_overlap_is_rejected(self):
        train = build_wallet_graph(toy_transactions(), "train")
        distinct = toy_transactions()
        for column in ["TRANSACTION_HASH", "SENDER", "RECEIVER"]:
            distinct[column] = "v_" + distinct[column]
        validation = build_wallet_graph(distinct, "validation")
        checks = assert_split_separation({"train": train, "validation": validation})
        self.assertEqual(checks["train/validation"], {"shared_transaction_hashes": 0, "shared_wallets": 0})
        for column in ["TRANSACTION_HASH", "SENDER"]:
            bad = distinct.copy()
            bad.loc[0, column] = toy_transactions().loc[0, column]
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, "Mixed split"):
                assert_split_separation({"train": train, "validation": build_wallet_graph(bad, "validation")})

    def test_original_direction_timestamps_and_coverage_are_checked(self):
        frame = toy_transactions()
        raw = frame[["TRANSACTION_HASH", "TIMESTAMP", "SENDER"]].rename(columns={"SENDER": "ACCOUNT"})
        raw["EXTRA_TRANSACTION_FIELDS"] = frame.RECEIVER.map(lambda x: json.dumps({"Destination": x}))
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "transactions.parquet"
            raw.to_parquet(original, index=False)
            validate_against_original(build_wallet_graph(frame, "train"), original)
            for column, value, message in [("SENDER", "wrong", "sender direction"),
                                            ("RECEIVER", "wrong", "receiver direction"),
                                            ("TIMESTAMP", 999, "timestamps")]:
                bad = frame.copy(); bad.loc[0, column] = value
                with self.subTest(column=column), self.assertRaisesRegex(ValueError, message):
                    validate_against_original(build_wallet_graph(bad, "train"), original)
            with self.assertRaisesRegex(ValueError, "coverage mismatch"):
                validate_against_original(build_wallet_graph(frame.iloc[:-1], "train"), original)

    def test_lossless_reload_checks_split_and_artifact_integrity(self):
        graph = build_wallet_graph(toy_transactions(), "train")
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            graph.edges.to_parquet(directory / "edges.parquet", index=False)
            graph.nodes.to_parquet(directory / "nodes.parquet", index=False)
            manifest = {"split": "train", "transaction_edges": 6, "wallet_nodes": 4,
                        "artifact_sha256": {n: sha256(directory / n) for n in ["edges.parquet", "nodes.parquet"]}}
            (directory / "manifest.json").write_text(json.dumps(manifest))
            restored = load_wallet_graph(directory, "train")
            assert_frame_equal(graph.edges, restored.edges, check_exact=True)
            assert_frame_equal(graph.nodes, restored.nodes, check_exact=True)
            assert_frame_equal(graph.outgoing("A"), restored.outgoing("A"), check_exact=True)
            with self.assertRaisesRegex(ValueError, "another split"):
                load_wallet_graph(directory, "test")
            with (directory / "edges.parquet").open("ab") as stream:
                stream.write(b"corruption")
            with self.assertRaisesRegex(ValueError, "Corrupt graph artifact"):
                load_wallet_graph(directory, "train")


if __name__ == "__main__":
    unittest.main()
