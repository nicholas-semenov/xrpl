"""Hand-built motifs test descriptions, strict timing, amounts and no supervision."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pyarrow as pa
import pyarrow.parquet as pq

from feature_workspace.aml_patterns import Thresholds, detect_patterns
from feature_workspace.build_wallet_graph import build_wallet_graph
from feature_workspace.prepare_aml_features import feature_table
from feature_workspace.prepare_transactions import COLUMNS


def frame(rows):
    records = []
    for hash_, timestamp, sender, receiver, amount in rows:
        records.append({"TRANSACTION_HASH": hash_, "TIMESTAMP": timestamp, "SENDER": sender, "RECEIVER": receiver,
                        "SOURCE_ASSET": "XRP", "DESTINATION_ASSET": "XRP", "SOURCE_AMOUNT": float(amount),
                        "DESTINATION_AMOUNT": float(amount), "SOURCE_AMOUNT_USD": float(amount),
                        "DESTINATION_AMOUNT_USD": float(amount), "TRANSFER_COUNT": 1, "IS_CONVERSION": False,
                        "CONVERSION_STEP_COUNT": 0, "INTERMEDIARY_COUNT": 0, "FEE_XRP": .00001})
    return pd.DataFrame(records).loc[:, COLUMNS]


def run(rows, cfg=None):
    graph = build_wallet_graph(frame(rows), "train")
    result, info = detect_patterns(graph, cfg or Thresholds())
    return result.set_index("TRANSACTION_HASH"), info


def scatter_rows(delay=100):
    return [(f"in{i}", 0, "S", f"M{i}", 100.) for i in range(3)] + [
        (f"out{i}", delay, f"M{i}", "D", 95.) for i in range(3)]


def hub_rows():
    return [(f"in{i}", i * 10, f"A{i}", "H", 100.) for i in range(3)] + [
        (f"out{i}", 50 + i * 10, "H", f"D{i}", 100.) for i in range(3)]


class AMLPatternTests(unittest.TestCase):
    def test_fan_in_fan_out_gather_scatter_and_overlapping_ids(self):
        result, info = run(hub_rows())
        for i in range(3):
            self.assertEqual(result.loc[f"in{i}", "aml_pattern"], [1, 4])
            self.assertEqual(result.loc[f"out{i}", "aml_pattern"], [2, 4])
        self.assertEqual(info["pattern_transaction_counts"], {"1": 3, "2": 3, "3": 0, "4": 6})
        self.assertEqual(result.loc["in0", "fan_in_1h_counterparty_count"], 3)
        self.assertEqual(result.loc["out0", "fan_out_1h_volume_usd"], 300.)
        self.assertEqual(result.loc["in0", "gather_scatter_1h_path_count"], 9)
        self.assertEqual(result.loc["in0", "gather_scatter_1h_flow_ratio"], 1.)
        self.assertEqual(result.loc["in0", "gather_scatter_1h_min_delay_seconds"], 30.)
        self.assertEqual(result.loc["out0", "sender_prior_in_count_1h"], 3)
        self.assertEqual(result.loc["in0", "receiver_future_out_count_1h"], 3)

    def test_repeated_counterparty_and_self_payments_do_not_inflate_fans(self):
        result, _ = run([(f"x{i}", i, "A", "H", 100.) for i in range(4)])
        self.assertTrue(all(ids == [] for ids in result.aml_pattern))
        result, _ = run([("a", 0, "A", "H", 100.), ("b", 1, "B", "H", 100.),
                         ("self", 2, "H", "H", 1000.)])
        self.assertTrue(all(ids == [] for ids in result.aml_pattern))
        self.assertEqual(result.loc["self", "receiver_in_unique_wallets_1h"], 2)

    def test_scatter_gather_requires_three_distinct_intermediaries(self):
        result, info = run(scatter_rows())
        self.assertEqual(info["pattern_transaction_counts"]["3"], 6)
        self.assertTrue(all(3 in ids for ids in result.aml_pattern))
        self.assertEqual(result.loc["in0", "scatter_gather_1h_path_count"], 3)
        self.assertEqual(result.loc["in0", "scatter_gather_1h_intermediary_count"], 3)
        self.assertAlmostEqual(result.loc["in0", "scatter_gather_1h_flow_ratio"], .95)
        self.assertEqual(result.loc["in0", "forward_path_min_delay_seconds_1h"], 100.)
        rows = [(f"in{i}", i, "S", "M", 100.) for i in range(3)] + [
            (f"out{i}", i + 100, "M", "D", 95.) for i in range(3)]
        result, _ = run(rows)
        self.assertFalse(any(3 in ids for ids in result.aml_pattern))

    def test_scatter_gather_deduplicates_event_amounts_not_path_counts(self):
        rows = [(f"in{i}", 0, "S", f"M{i}", 100.) for i in range(3)] + [
            ("a", 100, "M0", "D", 60.), ("b", 110, "M0", "D", 60.),
            ("c", 100, "M1", "D", 100.), ("d", 100, "M2", "D", 100.)]
        result, _ = run(rows)
        self.assertEqual(result.loc["in0", "scatter_gather_1h_path_count"], 4)
        self.assertAlmostEqual(result.loc["in0", "scatter_gather_1h_flow_ratio"], 320 / 300)

    def test_strict_time_order_and_equal_timestamp_exclusion(self):
        for delay in [-1, 0]:
            result, _ = run(scatter_rows(delay))
            self.assertFalse(any(3 in ids for ids in result.aml_pattern))
            self.assertEqual(result.loc["in0", "forward_compatible_path_count_1h"], 0)
        reversed_hub = [(h, -t, s, r, a) for h, t, s, r, a in hub_rows()]
        result, _ = run(reversed_hub)
        self.assertFalse(any(4 in ids for ids in result.aml_pattern))

    def test_windows_include_boundary_and_enforce_total_scatter_span(self):
        result, _ = run(scatter_rows(3600))
        self.assertTrue(result.scatter_gather_1h_detected.eq(1).all())
        result, _ = run(scatter_rows(3601))
        self.assertTrue(result.scatter_gather_1h_detected.eq(0).all())
        self.assertTrue(result.scatter_gather_24h_detected.eq(1).all())
        rows = [(f"in{i}", i * 3500, "S", f"M{i}", 100.) for i in range(3)] + [
            (f"out{i}", i * 3500 + 100, f"M{i}", "D", 95.) for i in range(3)]
        result, _ = run(rows)
        self.assertTrue(result.scatter_gather_1h_detected.eq(0).all())
        self.assertTrue(result.scatter_gather_24h_detected.eq(1).all())
        result, _ = run(scatter_rows(86401))
        self.assertTrue(result.scatter_gather_24h_detected.eq(0).all())
        self.assertTrue(result.scatter_gather_7d_detected.eq(1).all())
        result, _ = run(scatter_rows(604800))
        self.assertTrue(result.scatter_gather_7d_detected.eq(1).all())
        result, _ = run(scatter_rows(604801))
        self.assertTrue(result.scatter_gather_7d_detected.eq(0).all())

    def test_gather_scatter_uses_aggregate_funds_and_total_window_span(self):
        rows = [(f"in{i}", -2000 + i * 1000, f"A{i}", "H", 100.) for i in range(3)] + [
            ("out0", 100, "H", "D0", 10.), ("out1", 200, "H", "D1", 20.),
            ("out2", 1000, "H", "D2", 270.)]
        result, _ = run(rows)
        self.assertTrue(result.gather_scatter_1h_detected.eq(1).all())
        self.assertEqual(result.loc["in0", "forward_compatible_path_count_1h"], 0)
        self.assertEqual(result.loc["in0", "gather_scatter_1h_flow_ratio"], 1.)
        rows[-1] = ("out2", 2000, "H", "D2", 270.)  # Whole 4000-second span exceeds 1h.
        result, _ = run(rows)
        self.assertTrue(result.gather_scatter_1h_detected.eq(0).all())
        self.assertTrue(result.gather_scatter_24h_detected.eq(1).all())

    def test_amount_thresholds_and_resource_limits_fail_without_sampling(self):
        result, _ = run(hub_rows(), replace(Thresholds(), min_group_usd=1000.))
        self.assertTrue(all(ids == [] for ids in result.aml_pattern))
        with self.assertRaisesRegex(ValueError, "Resource limit exceeded: candidate_path_pairs"):
            run(hub_rows(), replace(Thresholds(), max_candidate_path_pairs=1))
        with self.assertRaisesRegex(ValueError, "Resource limit exceeded: witness_memberships"):
            run(hub_rows(), replace(Thresholds(), max_witness_memberships=1))
        with self.assertRaisesRegex(ValueError, "Resource limit exceeded: scatter_gather_path_checks"):
            run(scatter_rows(), replace(Thresholds(), max_scatter_gather_path_checks=1))
        with self.assertRaises(ValueError):
            run(hub_rows(), replace(Thresholds(), min_flow_ratio=2.))

    def test_original_fields_annotation_neutrality_determinism_and_numeric_schema(self):
        source = frame(hub_rows())
        original = source.copy(deep=True)
        graph = build_wallet_graph(source, "train")
        reference, info = detect_patterns(graph, Thresholds())
        contaminated = source.assign(is_suspicious=1, family="private", difficulty="hard",
                                      scenario_id="private", cohort_id="private")
        other, other_info = detect_patterns(build_wallet_graph(contaminated.sample(frac=1, random_state=9), "train"), Thresholds())
        assert_frame_equal(reference, other, check_exact=True)
        self.assertEqual(info, other_info)
        assert_frame_equal(source, original, check_exact=True)
        assert_frame_equal(reference[COLUMNS], graph.edges[COLUMNS], check_exact=True)
        self.assertTrue(np.isfinite(reference[info["numeric_feature_columns"]].to_numpy()).all())
        self.assertFalse({"is_suspicious", "family", "scenario_id", "cohort_id"} & set(reference.columns))

    def test_arrow_list_type_and_lossless_roundtrip_including_empty_lists(self):
        for rows in [hub_rows(), [("x", 0, "A", "B", 100.)]]:
            result, _ = detect_patterns(build_wallet_graph(frame(rows), "train"), Thresholds())
            table = feature_table(result)
            self.assertEqual(table.schema.field("aml_pattern").type, pa.list_(pa.int8()))
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "features.parquet"
                pq.write_table(table, path)
                self.assertTrue(pq.read_table(path).equals(table))


if __name__ == "__main__":
    unittest.main()
