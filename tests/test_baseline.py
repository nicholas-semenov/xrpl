"""Focused checks for baseline leakage controls, starter parity and scoring."""
import ast
import json
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.baseline import (FEATURES, ROOT, build_model, evaluate, isolated_split,
                              make_features, validate_predictions)


def toy_payments():
    return pd.DataFrame({
        "TRANSACTION_HASH": ["a", "b", "c", "d", "e", "f"],
        "TIMESTAMP": [0, 300, 600, 900, 3600, 5000],
        "FROM_ADDRESS": ["A", "B", "A", "C", "D", "A"],
        "TO_ADDRESS": ["B", "C", "D", "A", "B", "D"],
        "VALUE": [100., 95., 40., 90., 38., 200.],
    })


class BaselineTests(unittest.TestCase):
    def test_feature_parity_with_supplied_notebook(self):
        notebook = json.loads((ROOT / "data/traning_data/starter_notebook.ipynb").read_text())
        tree = ast.parse("".join(notebook["cells"][5]["source"]))
        # Execute only the two supplied function definitions, never notebook I/O.
        functions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
        namespace = {"np": np, "pd": pd, "HOUR": 3600, "TEN_MINUTES": 600}
        exec(compile(functions, "supplied_starter_functions", "exec"), namespace)
        expected = namespace["make_features"](toy_payments()).set_index("TRANSACTION_HASH")
        assert_frame_equal(make_features(toy_payments()), expected)

    def test_labels_and_annotations_cannot_change_features(self):
        clean = toy_payments()
        contaminated = clean.assign(is_suspicious=[0, 1, 1, 0, 1, 0],
                                    family="secret", scenario_id="secret", cohort_id="secret", difficulty="hard")
        assert_frame_equal(make_features(clean), make_features(contaminated))
        self.assertEqual(tuple(make_features(contaminated).columns), FEATURES)

    def test_time_direction_and_exact_one_hour_boundaries(self):
        df = pd.DataFrame({"TRANSACTION_HASH": ["before", "receipt", "same", "boundary", "late"],
                           "TIMESTAMP": [99, 100, 100, 3700, 3701],
                           "FROM_ADDRESS": ["B", "A", "B", "B", "B"],
                           "TO_ADDRESS": ["C", "B", "D", "E", "F"],
                           "VALUE": [100., 100., 100., 100., 100.]})
        f = make_features(df).loc["receipt"]
        self.assertEqual(f.receiver_minutes_to_forward, 60.)
        self.assertEqual(f.receiver_forwards_similar_1h, 1.)  # includes exactly +1h
        self.assertEqual(f.receiver_forwards_1h, 1.)  # starter includes equal-time sends
        earlier_only = df.iloc[:2]
        self.assertEqual(make_features(earlier_only).loc["receipt", "receiver_forwards_similar_1h"], 0.)

    def test_split_excludes_wallet_scenario_cohort_and_is_target_independent(self):
        wallets = [f"w{i}" for i in range(10)]
        rows = [(f"tx{i}_{j}", i, j) for i in wallets for j in wallets if i != j]
        df = pd.DataFrame(rows, columns=["TRANSACTION_HASH", "FROM_ADDRESS", "TO_ADDRESS"])
        annotations = pd.DataFrame({"TRANSACTION_HASH": df.TRANSACTION_HASH,
                                    "scenario_id": df.TRANSACTION_HASH, "cohort_id": None,
                                    "is_suspicious": 0})
        initial = isolated_split(df, annotations)
        fit_ids = initial.loc[initial.partition.eq("fit"), "TRANSACTION_HASH"].head(2).tolist()
        hold_ids = initial.loc[initial.partition.eq("holdout"), "TRANSACTION_HASH"].head(2).tolist()
        annotations.loc[annotations.TRANSACTION_HASH.isin([fit_ids[0], hold_ids[0]]), "scenario_id"] = "shared"
        annotations.loc[annotations.TRANSACTION_HASH.isin([fit_ids[1], hold_ids[1]]), "cohort_id"] = "shared"
        split = isolated_split(df, annotations)
        reason = split.set_index("TRANSACTION_HASH").purge_reason
        self.assertEqual(reason[fit_ids[0]], "shared_scenario_id")
        self.assertEqual(reason[fit_ids[1]], "shared_cohort_id")
        assigned = df.merge(split, on="TRANSACTION_HASH")
        fit = assigned.loc[assigned.partition.eq("fit")]
        hold = assigned.loc[assigned.partition.eq("holdout")]
        self.assertFalse((set(fit.FROM_ADDRESS) | set(fit.TO_ADDRESS)) &
                         (set(hold.FROM_ADDRESS) | set(hold.TO_ADDRESS)))
        annotations["is_suspicious"] = 1
        assert_frame_equal(split, isolated_split(df.sample(frac=1, random_state=3), annotations.sample(frac=1, random_state=4)))

    def test_scaling_does_not_fit_on_holdout_outliers(self):
        x_fit = pd.DataFrame({"x": [0., 1., 2., 3.]})
        model = build_model()
        model.fit(x_fit, [0, 0, 1, 1])
        before = model[0].mean_.copy()
        model.predict_proba(pd.DataFrame({"x": [1e12]}))
        np.testing.assert_array_equal(model[0].mean_, before)
        self.assertEqual(model[0].mean_[0], 1.5)

    def test_metrics_alignment_budget_ties_and_invalid_coverage(self):
        # At a tied top score, ascending hash selects the positive "a".
        p = pd.DataFrame({"TRANSACTION_HASH": ["b", "a", "c"], "score": [0.9, 0.9, 0.1]})
        y = pd.Series([0, 1, 0], index=["b", "a", "c"])
        metrics = evaluate(p, y)
        self.assertEqual(metrics["average_precision"], 0.5)
        self.assertEqual(metrics["roc_auc"], 0.75)
        self.assertEqual(metrics["top_1pct_count"], 1)
        self.assertEqual(metrics["precision_at_1pct"], 1.)
        self.assertEqual(metrics["recall_at_1pct"], 1.)
        self.assertEqual(metrics, evaluate(p.iloc[::-1], y.iloc[::-1]))
        invalid = p.copy()
        invalid.loc[0, "TRANSACTION_HASH"] = "unknown"
        with self.assertRaises(ValueError):
            validate_predictions(invalid, y.index)
        invalid = p.copy()
        invalid.loc[0, "score"] = np.nan
        with self.assertRaises(ValueError):
            validate_predictions(invalid, y.index)


if __name__ == "__main__":
    unittest.main()
