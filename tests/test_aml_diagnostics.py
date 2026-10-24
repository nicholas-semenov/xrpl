"""Hand-calculated diagnostic metrics, safe target alignment and exact duplicates."""
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from feature_workspace.diagnose_aml_train import (align_targets, binary_metrics,
                                                  exact_duplicate_groups, pattern_metrics, profile_features)


class AMLDiagnosticTests(unittest.TestCase):
    def test_hand_calculated_precision_recall_lift_and_empty_detection(self):
        y = np.array([1, 0, 1, 0])
        metrics = binary_metrics(np.array([1, 1, 1, 0]), y)
        self.assertEqual(metrics["true_positives"], 2)
        self.assertEqual(metrics["false_positives"], 1)
        self.assertEqual(metrics["false_negatives"], 0)
        self.assertEqual(metrics["true_negatives"], 1)
        self.assertAlmostEqual(metrics["precision"], 2 / 3)
        self.assertEqual(metrics["recall"], 1.)
        self.assertAlmostEqual(metrics["lift_vs_exact_prevalence"], 4 / 3)
        self.assertAlmostEqual(metrics["lift_vs_3_11pct"], (2 / 3) / .0311)
        empty = binary_metrics(np.zeros(4), y)
        self.assertIsNone(empty["precision"])
        self.assertIsNone(empty["lift_vs_exact_prevalence"])
        self.assertEqual(empty["recall"], 0.)
        self.assertEqual(binary_metrics(np.ones(4), y)["lift_vs_exact_prevalence"], 1.)

    def test_targets_align_by_hash_without_mutation_or_positional_join(self):
        frame = pd.DataFrame({"TRANSACTION_HASH": ["b", "a", "c"]})
        labels = pd.DataFrame({"TRANSACTION_HASH": ["a", "c", "b"], "is_suspicious": [1, 0, 0]})
        before = labels.copy(deep=True)
        self.assertEqual(align_targets(frame, labels).tolist(), [0, 1, 0])
        assert_frame_equal(labels, before)
        with self.assertRaisesRegex(ValueError, "coverage"):
            align_targets(frame, labels.iloc[:-1])
        with self.assertRaisesRegex(ValueError, "unique"):
            align_targets(frame, pd.concat([labels, labels.iloc[:1]]))
        bad = labels.copy(); bad.loc[0, "is_suspicious"] = 2
        with self.assertRaisesRegex(ValueError, "binary"):
            align_targets(frame, bad)

    def test_profile_distinguishes_constant_sparse_sentinel_and_exact_duplicates(self):
        frame = pd.DataFrame({"constant": [1, 1, 1, 1], "same_constant": [1., 1., 1., 1.],
                              "x": [0, 1, 2, 3], "same_x": [0., 1., 2., 3.],
                              "correlated_not_duplicate": [0., 2., 4., 6.],
                              "funding_delay_seconds": [-1., -1., 10., 20.]})
        original = frame.copy(deep=True)
        q = profile_features(frame, frame.columns.tolist(), pd.Series([0, 1, 0, 1]))
        self.assertEqual(q["constant_columns"], ["constant", "same_constant"])
        self.assertEqual(q["nonconstant_duplicate_groups"], [["x", "same_x"]])
        self.assertEqual(q["distinct_nonconstant_numeric_columns"], 3)
        delay = q["profiles"]["funding_delay_seconds"]
        self.assertEqual(delay["delay_sentinel_fraction"], .5)
        self.assertEqual(delay["excluding_delay_sentinel"]["quantiles"]["0.5"], 15.)
        self.assertEqual(q["total_unexpected_negative_values"], 0)
        assert_frame_equal(frame, original)
        sparse = pd.DataFrame({"sparse": [0.] * 99 + [1.]})
        self.assertEqual(profile_features(sparse, ["sparse"], pd.Series([0] * 99 + [1]))[
            "near_constant_columns_99pct"], ["sparse"])

    def test_duplicate_comparison_handles_signed_zero_nan_and_rejects_large_integers(self):
        frame = pd.DataFrame({"a": [0., np.nan, 1.], "b": [-0., np.nan, 1.], "c": [0., np.nan, 2.]})
        self.assertEqual(exact_duplicate_groups(frame, list(frame)), [["a", "b"]])
        with self.assertRaisesRegex(ValueError, "Integer too large"):
            exact_duplicate_groups(pd.DataFrame({"huge": [2**53 + 1]}), ["huge"])

    def test_all_pattern_window_masks_and_union_membership_are_consistent(self):
        names = ["fan_in", "fan_out", "scatter_gather", "gather_scatter"]
        frame = pd.DataFrame({f"{name}_{window}_detected": [1, 0, 0]
                              for name in names for window in ["1h", "24h", "7d"]})
        frame["aml_pattern"] = [[1, 2, 3, 4], [], []]
        rows, unions = pattern_metrics(frame, pd.Series([1, 0, 0]))
        self.assertEqual(len(rows), 12)
        self.assertEqual(len(unions), 4)
        self.assertEqual(rows[0]["precision"], 1.)
        frame.at[0, "aml_pattern"] = [1, 2]  # Deliberately inconsistent saved metadata.
        with self.assertRaisesRegex(ValueError, "Pattern list/window flags"):
            pattern_metrics(frame, pd.Series([1, 0, 0]))


if __name__ == "__main__":
    unittest.main()
