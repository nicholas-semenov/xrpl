"""Starter logistic baseline with isolated wallet/scenario/cohort holdout.

The twelve features and estimator follow the supplied starter_notebook.ipynb.
Only the labelled train directory is read. No advanced motif detection is added.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data/traning_data/train"
FEATURES = (
    "log_value", "sender_payments", "receiver_payments", "receiver_forwards_1h",
    "sender_received_1h_before", "sender_burst_10m", "receiver_burst_10m",
    "receiver_forwards_similar_1h", "sender_received_similar_1h",
    "receiver_minutes_to_forward", "sender_pass_through", "receiver_pass_through",
)
PAYMENT_COLUMNS = ("TRANSACTION_HASH", "TIMESTAMP", "FROM_ADDRESS", "TO_ADDRESS", "VALUE")


def require(condition: bool, message: str) -> None:
    """Keep integrity checks active even under optimized Python execution."""
    if not condition:
        raise ValueError(message)


def load_training() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read only supplied train payments and labels, validating exact coverage."""
    helper = TRAIN.parent / "payments.py"
    spec = importlib.util.spec_from_file_location("supplied_payments", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payments = pd.DataFrame(module.load_payments(TRAIN)).loc[:, list(PAYMENT_COLUMNS)]
    annotations = pd.read_csv(TRAIN / "labels.csv")
    for frame in (payments, annotations):
        require(frame.TRANSACTION_HASH.notna().all() and frame.TRANSACTION_HASH.is_unique,
                "Transaction keys must be non-null and unique")
    require(set(payments.TRANSACTION_HASH) == set(annotations.TRANSACTION_HASH),
            "Labels must cover exactly the supplied train payments")
    require(annotations.is_suspicious.isin([0, 1]).all(), "Target must be binary")
    require(payments.notna().all().all(), "Required payment fields cannot be null")
    require(np.isfinite(payments.VALUE).all() and payments.VALUE.gt(0).all(),
            "Payment USD values must be finite and positive")
    payments["TIMESTAMP"] = payments.TIMESTAMP.astype("int64")
    return payments, annotations


def isolated_split(payments: pd.DataFrame, annotations: pd.DataFrame,
                   seed: int = 0, holdout_wallet_fraction: float = 0.5) -> pd.DataFrame:
    """Select wallets without targets; purge cross edges and shared annotations.

    Group metadata is used only to exclude fit rows, never to compute features.
    Fit/holdout contexts subsequently contain only their retained payments.
    """
    require(0 < holdout_wallet_fraction < 1, "Wallet fraction must be between zero and one")
    frame = payments[["TRANSACTION_HASH", "FROM_ADDRESS", "TO_ADDRESS"]].merge(
        annotations[["TRANSACTION_HASH", "scenario_id", "cohort_id"]],
        on="TRANSACTION_HASH", how="left", validate="one_to_one", indicator=True)
    require(frame._merge.eq("both").all(), "Missing split annotations")
    wallets = sorted(set(frame.FROM_ADDRESS) | set(frame.TO_ADDRESS))
    n_holdout = math.ceil(len(wallets) * holdout_wallet_fraction)
    require(0 < n_holdout < len(wallets), "Need wallets in both partitions")
    holdout_wallets = set(np.random.default_rng(seed).permutation(wallets)[:n_holdout])
    source_in = frame.FROM_ADDRESS.isin(holdout_wallets)
    dest_in = frame.TO_ADDRESS.isin(holdout_wallets)
    frame["partition"] = np.where(source_in & dest_in, "holdout",
                                  np.where(~source_in & ~dest_in, "fit", "purged"))
    frame["purge_reason"] = np.where(frame.partition.eq("purged"), "cross_wallet", "")
    for column in ("scenario_id", "cohort_id"):
        holdout_groups = set(frame.loc[frame.partition.eq("holdout"), column].dropna())
        remove = frame.partition.eq("fit") & frame[column].isin(holdout_groups)
        frame.loc[remove, "partition"] = "purged"
        frame.loc[remove, "purge_reason"] = f"shared_{column}"
    fit = frame.loc[frame.partition.eq("fit")]
    holdout = frame.loc[frame.partition.eq("holdout")]
    require(len(fit) > 0 and len(holdout) > 0, "Empty isolated partition")
    fit_wallets = set(fit.FROM_ADDRESS) | set(fit.TO_ADDRESS)
    check_wallets = set(holdout.FROM_ADDRESS) | set(holdout.TO_ADDRESS)
    require(not fit_wallets & check_wallets, "Wallet leakage between partitions")
    for column in ("scenario_id", "cohort_id"):
        require(not set(fit[column].dropna()) & set(holdout[column].dropna()),
                f"Shared {column} between partitions")
    return frame[["TRANSACTION_HASH", "partition", "purge_reason"]].sort_values(
        "TRANSACTION_HASH").reset_index(drop=True)


def make_features(payments: pd.DataFrame) -> pd.DataFrame:
    """Compute only starter features from this partition's unlabeled payments.

    Whole-window context is permitted by the dataset README. Stable hash ordering
    resolves timestamp ties; equal-time boundary conventions follow the notebook.
    """
    df = payments.loc[:, list(PAYMENT_COLUMNS)].copy()
    require(df.TRANSACTION_HASH.is_unique, "Duplicate feature transaction")
    df = df.sort_values(["TIMESTAMP", "TRANSACTION_HASH"]).reset_index(drop=True)
    t = df.TIMESTAMP.astype("int64").to_numpy()
    value = df.VALUE.to_numpy()
    sends = {a: g.TIMESTAMP.astype("int64").to_numpy() for a, g in df.groupby("FROM_ADDRESS")}
    gets = {a: g.TIMESTAMP.astype("int64").to_numpy() for a, g in df.groupby("TO_ADDRESS")}
    sent_values = {a: g.VALUE.to_numpy() for a, g in df.groupby("FROM_ADDRESS")}
    got_values = {a: g.VALUE.to_numpy() for a, g in df.groupby("TO_ADDRESS")}

    def count(history: dict, account: str, ti: int, before: int, after: int) -> int:
        times = history.get(account)
        if times is None:
            return 0
        return int(np.searchsorted(times, ti + after, "right") -
                   np.searchsorted(times, ti - before, "left"))

    def similar(account: str, ti: int, amount: float, forward: bool) -> bool:
        times = (sends if forward else gets).get(account)
        if times is None:
            return False
        if forward:
            lo, hi = np.searchsorted(times, ti, "right"), np.searchsorted(times, ti + 3600, "right")
        else:
            lo, hi = np.searchsorted(times, ti - 3600, "left"), np.searchsorted(times, ti, "left")
        values = (sent_values if forward else got_values)[account][lo:hi]
        return bool(np.any(np.abs(values - amount) <= 0.1 * amount))

    def next_send(account: str, ti: int) -> float:
        times = sends.get(account)
        if times is None:
            return 60.0
        i = np.searchsorted(times, ti, "right")
        return min(60.0, (times[i] - ti) / 60) if i < len(times) else 60.0

    f = pd.DataFrame({"TRANSACTION_HASH": df.TRANSACTION_HASH})
    f["log_value"] = np.log1p(value)
    f["sender_payments"] = df.FROM_ADDRESS.map(df.FROM_ADDRESS.value_counts())
    f["receiver_payments"] = df.TO_ADDRESS.map(df.TO_ADDRESS.value_counts())
    f["receiver_forwards_1h"] = [count(sends, a, ti, 0, 3600) > 0 for a, ti in zip(df.TO_ADDRESS, t)]
    f["sender_received_1h_before"] = [count(gets, a, ti, 3600, 0) > 0 for a, ti in zip(df.FROM_ADDRESS, t)]
    f["sender_burst_10m"] = [count(sends, a, ti, 600, 600) for a, ti in zip(df.FROM_ADDRESS, t)]
    f["receiver_burst_10m"] = [count(gets, a, ti, 600, 600) for a, ti in zip(df.TO_ADDRESS, t)]
    f["receiver_forwards_similar_1h"] = [similar(a, ti, v, True) for a, ti, v in zip(df.TO_ADDRESS, t, value)]
    f["sender_received_similar_1h"] = [similar(a, ti, v, False) for a, ti, v in zip(df.FROM_ADDRESS, t, value)]
    f["receiver_minutes_to_forward"] = [next_send(a, ti) for a, ti in zip(df.TO_ADDRESS, t)]
    sent_total = df.groupby("FROM_ADDRESS").VALUE.sum()
    got_total = df.groupby("TO_ADDRESS").VALUE.sum()
    pass_through = (sent_total / got_total.reindex(sent_total.index)).clip(0, 3)
    f["sender_pass_through"] = df.FROM_ADDRESS.map(pass_through).fillna(0)
    f["receiver_pass_through"] = df.TO_ADDRESS.map(pass_through).fillna(0)
    f = f.set_index("TRANSACTION_HASH").loc[:, list(FEATURES)].astype(float)
    require(np.isfinite(f.to_numpy()).all(), "Non-finite features")
    return f


def build_model(seed: int = 0):
    """Use the starter algorithm; fit scaling and class weights on fit rows only."""
    return make_pipeline(StandardScaler(), LogisticRegression(
        class_weight="balanced", max_iter=1000, solver="lbfgs", C=1.0,
        tol=1e-4, random_state=seed))


def validate_predictions(predictions: pd.DataFrame, expected: pd.Index) -> None:
    """Check exact hash-to-score coverage before and after CSV serialization."""
    require(list(predictions.columns) == ["TRANSACTION_HASH", "score"], "Wrong score columns")
    require(predictions.TRANSACTION_HASH.notna().all() and predictions.TRANSACTION_HASH.is_unique,
            "Null or duplicate prediction keys")
    require(len(predictions) == len(expected) and set(predictions.TRANSACTION_HASH) == set(expected),
            "Wrong prediction coverage")
    require(pd.api.types.is_numeric_dtype(predictions.score), "Non-numeric scores")
    require(np.isfinite(predictions.score).all() and predictions.score.between(0, 1).all(),
            "Scores must be finite and in [0, 1]")


def evaluate(predictions: pd.DataFrame, targets: pd.Series) -> dict:
    """Compute AP, AUC and exact-budget top 1%, breaking ties by hash ascending."""
    validate_predictions(predictions, targets.index)
    y = targets.loc[predictions.TRANSACTION_HASH].to_numpy()
    require(set(y) == {0, 1}, "Evaluation requires both target classes")
    k = math.ceil(len(predictions) * 0.01)
    top = predictions.sort_values(["score", "TRANSACTION_HASH"], ascending=[False, True]).head(k)
    positives = int(y.sum())
    true_positives = int(targets.loc[top.TRANSACTION_HASH].sum())
    ap = float(average_precision_score(y, predictions.score))
    return {"average_precision": ap, "challenge_score_100_ap": 100 * ap,
            "roc_auc": float(roc_auc_score(y, predictions.score)),
            "precision_at_1pct": true_positives / k, "recall_at_1pct": true_positives / positives,
            "top_1pct_count": k, "top_1pct_true_positives": true_positives,
            "holdout_positives": positives, "holdout_positive_fraction": float(y.mean()),
            "score_min": float(predictions.score.min()), "score_max": float(predictions.score.max()),
            "distinct_scores": int(predictions.score.nunique())}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output_dir: Path, report_path: Path, seed: int = 0) -> dict:
    """Fit once and evaluate the fixed holdout; persist artifacts and provenance."""
    started = time.perf_counter()
    payments, annotations = load_training()
    split = isolated_split(payments, annotations, seed=seed)
    # Do not let annotation fields or purged payments enter either feature context.
    assigned = payments.merge(split, on="TRANSACTION_HASH", validate="one_to_one")
    fit_payments = assigned.loc[assigned.partition.eq("fit"), list(PAYMENT_COLUMNS)]
    holdout_payments = assigned.loc[assigned.partition.eq("holdout"), list(PAYMENT_COLUMNS)]
    feature_started = time.perf_counter()
    x_fit = make_features(fit_payments)
    x_holdout = make_features(holdout_payments)
    feature_seconds = time.perf_counter() - feature_started
    targets = annotations.set_index("TRANSACTION_HASH").is_suspicious
    y_fit = targets.loc[x_fit.index]
    require(set(y_fit) == {0, 1}, "Training requires both target classes")
    model = build_model(seed)
    fit_started = time.perf_counter()
    with warnings.catch_warnings(), threadpool_limits(limits=1):
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(x_fit, y_fit)
        scores = model.predict_proba(x_holdout)[:, 1]
    fit_seconds = time.perf_counter() - fit_started
    predictions = pd.DataFrame({"TRANSACTION_HASH": x_holdout.index, "score": scores})
    validate_predictions(predictions, x_holdout.index)
    output_dir.mkdir(parents=True, exist_ok=True)
    split.to_csv(output_dir / "split.csv", index=False)
    predictions.to_csv(output_dir / "holdout_predictions.csv", index=False, float_format="%.17g")
    reread = pd.read_csv(output_dir / "holdout_predictions.csv", float_precision="round_trip")
    validate_predictions(reread, x_holdout.index)
    require(reread.TRANSACTION_HASH.tolist() == predictions.TRANSACTION_HASH.tolist(),
            "Serialized prediction order changed")
    require(np.array_equal(reread.score.to_numpy(), scores), "Scores changed during serialization")
    joblib.dump(model, output_dir / "model.joblib")
    restored = joblib.load(output_dir / "model.joblib")
    with threadpool_limits(limits=1):
        require(np.array_equal(restored.predict_proba(x_holdout)[:, 1], scores),
                "Saved model predictions changed")
    counts = {}
    diagnostics = {}
    for name, ids in split.groupby("partition"):
        a = annotations.set_index("TRANSACTION_HASH").loc[ids.TRANSACTION_HASH]
        counts[name] = {"transactions": len(a), "positives": int(a.is_suspicious.sum()),
                        "positive_fraction": float(a.is_suspicious.mean()),
                        "scenarios": int(a.scenario_id.nunique()), "cohorts": int(a.cohort_id.nunique())}
        diagnostics[name] = {"difficulty_counts": a.difficulty.value_counts().to_dict()}
    fit_wallets = set(fit_payments.FROM_ADDRESS) | set(fit_payments.TO_ADDRESS)
    check_wallets = set(holdout_payments.FROM_ADDRESS) | set(holdout_payments.TO_ADDRESS)
    ann = annotations.set_index("TRANSACTION_HASH")
    group_overlaps = {c: len(set(ann.loc[x_fit.index, c].dropna()) &
                            set(ann.loc[x_holdout.index, c].dropna()))
                      for c in ("scenario_id", "cohort_id")}
    sources = [Path(__file__), TRAIN.parent / "payments.py", TRAIN.parent / "starter_notebook.ipynb",
               TRAIN / "transactions.parquet", TRAIN / "labels.csv", TRAIN / "market_rates.csv",
               ROOT / "requirements-baseline.txt"]
    report = {
        "run_id": f"starter_logistic_wallet_seed{seed}",
        "seed": seed, "algorithm": "StandardScaler + balanced L2 LogisticRegression",
        "model_parameters": model[-1].get_params(), "features": list(FEATURES),
        "split_protocol": {
            "holdout_wallet_fraction": 0.5, "wallet_assignment": "sorted wallets, numpy default_rng(seed).permutation",
            "purging": "Cross-wallet payments removed; fit rows sharing holdout scenario_id or cohort_id removed",
            "feature_context": "Separately retained fit / holdout payments; full window; purged rows excluded",
            "target_used_for_split": False, "counts": counts,
            "purge_reasons": split.loc[split.partition.eq("purged"), "purge_reason"].value_counts().to_dict(),
            "fit_wallets": len(fit_wallets), "holdout_wallets": len(check_wallets),
            "wallet_overlap": len(fit_wallets & check_wallets), "annotation_group_overlaps": group_overlaps,
            "transaction_overlap": len(set(x_fit.index) & set(x_holdout.index)),
        },
        "metrics": evaluate(reread, targets.loc[x_holdout.index]),
        "annotation_diagnostics_only": diagnostics,
        "standardized_coefficients": dict(zip(FEATURES, model[-1].coef_[0].tolist())),
        "intercept": float(model[-1].intercept_[0]),
        "solver_iterations": model[-1].n_iter_.tolist(),
        "versions": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "pyarrow", "scipy",
                     "scikit-learn", "joblib", "threadpoolctl"]},
        "python": platform.python_version(), "platform": platform.platform(), "blas_threads": 1,
        "timings_seconds": {"feature_generation": feature_seconds, "fit_and_predict": fit_seconds,
                            "total": time.perf_counter() - started},
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in sources},
        "artifact_sha256": {n: sha256(output_dir / n) for n in ["split.csv", "holdout_predictions.csv"]},
        "limitations": ["One fixed holdout; no uncertainty estimate or hyperparameter search",
                        "Purging removes many payments and truncates graphs/scenarios",
                        "Holdout is an induced subgraph, not an independent complete synthetic week",
                        "Offline features use later events within their own partition; not a causal benchmark",
                        "Only labelled train inputs used; no validation/test inference or competition score"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"split": counts, "metrics": report["metrics"],
                      "timings_seconds": report["timings_seconds"]}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/baseline_wallet_seed0")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/baseline_metrics.json")
    args = parser.parse_args()
    run(args.output_dir, args.report)
