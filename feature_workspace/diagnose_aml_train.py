"""Read-only train diagnostics of frozen AML outputs; never fit or tune detectors."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from feature_workspace.aml_patterns import PATTERNS, WINDOWS
from feature_workspace.paths import REPO_ROOT, output_path
from feature_workspace.prepare_transactions import require, sha256

ROUNDED_PREVALENCE = .0311


def align_targets(features: pd.DataFrame, labels: pd.DataFrame) -> pd.Series:
    """Align only the binary diagnostic target using exact one-to-one hash coverage."""
    for frame in (features, labels):
        require(frame.TRANSACTION_HASH.notna().all() and frame.TRANSACTION_HASH.is_unique,
                "Transaction hashes must be unique and non-null")
    require(set(features.TRANSACTION_HASH) == set(labels.TRANSACTION_HASH), "Label/hash coverage mismatch")
    require(labels.is_suspicious.isin([0, 1]).all(), "Labels must be binary")
    result = labels.set_index("TRANSACTION_HASH").is_suspicious.loc[features.TRANSACTION_HASH]
    result = result.reset_index(drop=True).astype("int64")
    require(0 < result.sum() < len(result), "Diagnostics need both target classes")
    return result


def binary_metrics(mask: np.ndarray, y: np.ndarray) -> dict:
    """Lift is precision/prevalence; undefined precision/lift is null, not zero."""
    require(len(y) > 0 and len(mask) == len(y) and np.isin(mask, [0, 1]).all() and np.isin(y, [0, 1]).all(),
            "Invalid binary mask or targets")
    mask = mask.astype(bool)
    tp, fp = int(((y == 1) & mask).sum()), int(((y == 0) & mask).sum())
    fn, tn = int(((y == 1) & ~mask).sum()), int(((y == 0) & ~mask).sum())
    detected, positives = int(mask.sum()), int(y.sum())
    prevalence = positives / len(y)
    precision = tp / detected if detected else None
    return {"detected": detected, "coverage": detected / len(y), "true_positives": tp,
            "false_positives": fp, "false_negatives": fn, "true_negatives": tn,
            "precision": precision, "recall": tp / positives if positives else None,
            "lift_vs_3_11pct": precision / ROUNDED_PREVALENCE if precision is not None else None,
            "lift_vs_exact_prevalence": precision / prevalence if precision is not None and prevalence else None}


def pattern_metrics(features: pd.DataFrame, targets: pd.Series) -> tuple[list, list]:
    rows, unions = [], []
    expected_memberships = [[] for _ in range(len(features))]
    y = targets.to_numpy()
    for pid, name in PATTERNS.items():
        masks = []
        for window in WINDOWS:
            mask = features[f"{name}_{window}_detected"].to_numpy()
            rows.append({"pattern_id": pid, "pattern": name, "window": window, **binary_metrics(mask, y)})
            masks.append(mask.astype(bool))
        union = np.logical_or.reduce(masks)
        unions.append({"pattern_id": pid, "pattern": name, "window": "any", **binary_metrics(union, y)})
        for i in np.flatnonzero(union):
            expected_memberships[i].append(pid)
    require(features.aml_pattern.map(list).tolist() == expected_memberships, "Pattern list/window flags mismatch")
    return rows, unions


def distribution(values: np.ndarray) -> dict:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return {"count": 0, "min": None, "max": None, "mean": None, "std_population": None, "quantiles": {}}
    qs = [.01, .05, .25, .5, .75, .95, .99]
    return {"count": len(finite), "min": float(finite.min()), "max": float(finite.max()),
            "mean": float(finite.mean()), "std_population": float(finite.std(ddof=0)),
            "quantiles": {str(q): float(v) for q, v in zip(qs, np.quantile(finite, qs))}}


def exact_duplicate_groups(features: pd.DataFrame, columns: list[str]) -> list[list[str]]:
    """Compare exact numeric float64 model values; normalize signed zero/NaN payloads.

    All current AML count columns fit exactly in float64. Hash buckets are always
    confirmed by full value comparison, so hash collisions cannot create duplicates.
    """
    buckets = {}
    groups = []
    arrays = {}
    for column in columns:
        values = features[column].to_numpy(dtype="float64", copy=True)
        if pd.api.types.is_integer_dtype(features[column]):
            require(features[column].between(-(2**53), 2**53).all(), "Integer too large for exact float64 duplicate check")
        values[values == 0] = 0.
        values[np.isnan(values)] = np.nan
        arrays[column] = values
        digest = hashlib.sha256(values.astype("<f8").tobytes()).hexdigest()
        matched = False
        for group in buckets.get(digest, []):
            if np.array_equal(values, arrays[group[0]], equal_nan=True):
                group.append(column)
                matched = True
                break
        if not matched:
            group = [column]
            buckets.setdefault(digest, []).append(group)
            groups.append(group)
    return [group for group in groups if len(group) > 1]


def profile_features(features: pd.DataFrame, columns: list[str], targets: pd.Series) -> dict:
    require(len(columns) == len(set(columns)), "Duplicate feature names in schema")
    profiles = {}
    for column in columns:
        require(pd.api.types.is_numeric_dtype(features[column]), f"Non-numeric AML feature: {column}")
        series = features[column]
        values = series.to_numpy(dtype="float64")
        counts = series.value_counts(dropna=False)
        is_delay = "delay_seconds" in column
        finite = np.isfinite(values)
        missing_delay = values == -1 if is_delay else np.zeros(len(values), dtype=bool)
        profile = {"dtype": str(series.dtype), "unique_values": int(series.nunique(dropna=False)),
                   "missing_count": int(series.isna().sum()), "infinite_count": int(np.isinf(values).sum()),
                   "zero_fraction": float((values == 0).mean()), "minus_one_count": int((values == -1).sum()),
                   "delay_sentinel_fraction": float(missing_delay.mean()) if is_delay else None,
                   "dominant_value": float(counts.index[0]) if pd.notna(counts.index[0]) else None,
                   "dominant_fraction": float(counts.iloc[0] / len(series)),
                   "unexpected_negative_count": int(((values < 0) & ~missing_delay).sum()),
                   "overall": distribution(values),
                   "excluding_delay_sentinel": distribution(values[~missing_delay]) if is_delay else None,
                   "by_diagnostic_class": {}}
        for label in [0, 1]:
            class_values = values[targets.to_numpy() == label]
            profile["by_diagnostic_class"][str(label)] = {
                **distribution(class_values), "zero_fraction": float((class_values == 0).mean()),
                "delay_sentinel_fraction": float((class_values == -1).mean()) if is_delay else None}
        profile["constant"] = profile["unique_values"] == 1
        profile["near_constant_99pct"] = not profile["constant"] and profile["dominant_fraction"] >= .99
        profile["finite_count"] = int(finite.sum())
        profiles[column] = profile
    constants = [c for c in columns if profiles[c]["constant"]]
    duplicates = exact_duplicate_groups(features, columns)
    nonconstant_duplicates = [g for g in duplicates if not profiles[g[0]]["constant"]]
    redundant = sum(len(g) - 1 for g in nonconstant_duplicates)
    return {"feature_count": len(columns), "profiles": profiles, "constant_columns": constants,
            "near_constant_columns_99pct": [c for c in columns if profiles[c]["near_constant_99pct"]],
            "duplicate_groups_including_constants": duplicates, "nonconstant_duplicate_groups": nonconstant_duplicates,
            "redundant_nonconstant_columns": redundant,
            "distinct_nonconstant_numeric_columns": len(columns) - len(constants) - redundant,
            "total_missing_values": sum(p["missing_count"] for p in profiles.values()),
            "total_infinite_values": sum(p["infinite_count"] for p in profiles.values()),
            "total_unexpected_negative_values": sum(p["unexpected_negative_count"] for p in profiles.values())}


def markdown_report(report: dict) -> str:
    quality = report["feature_quality"]
    lines = ["# Диагностика четырёх AML-детекторов на train", "",
             f"Воспроизведение: `{report['command']}`", "",
             f"Размечено {report['transactions']:,} транзакций: {report['positives']:,} подозрительных. "
             f"Фактическая базовая доля — **{100 * report['exact_prevalence']:.6f}%**; указанная округлённая — 3,11%.", "",
             "Precision = TP / найденные; recall = TP / все 1 250 положительных; lift = precision / базовая доля. "
             "Ниже основная нормировка lift — к указанным 3,11%; JSON также содержит нормировку к точной доле. "
             "TP означает любую подозрительную транзакцию, а не подтверждение правильности конкретной типологии. "
             "Аннотации family/difficulty/scenario/cohort не читались.", "",
             "| Паттерн | Окно | Найдено | TP | FP | Precision | Recall | Lift / 3,11% | Lift / точную долю |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in report["pattern_metrics"] + report["union_metrics"]:
        precision = f"{100 * row['precision']:.4f}%" if row["precision"] is not None else "—"
        lift = f"{row['lift_vs_3_11pct']:.4f}" if row["lift_vs_3_11pct"] is not None else "—"
        exact = f"{row['lift_vs_exact_prevalence']:.4f}" if row["lift_vs_exact_prevalence"] is not None else "—"
        lines.append(f"| {row['pattern_id']} {row['pattern']} | {row['window']} | {row['detected']:,} | "
                     f"{row['true_positives']:,} | {row['false_positives']:,} | {precision} | "
                     f"{100 * row['recall']:.4f}% | {lift} | {exact} |")
    lines += ["", "`any` — объединение окон для одного паттерна; пересекающиеся паттерны нельзя суммировать.", "",
              "## Выводы о детекторах", ""]
    for pid in PATTERNS:
        candidates = [r for r in report["pattern_metrics"] if r["pattern_id"] == pid and r["precision"] is not None]
        best = max(candidates, key=lambda r: r["lift_vs_exact_prevalence"])
        lines.append(f"- ID {pid} ({PATTERNS[pid]}): наибольшее наблюдаемое обогащение среди трёх окон — "
                     f"{best['window']}, precision {100 * best['precision']:.2f}%, recall {100 * best['recall']:.2f}%, "
                     f"lift к точной доле {best['lift_vs_exact_prevalence']:.2f}×. Это описание train, не выбор/изменение порога.")
    lines += ["- Семидневные fan-in/fan-out находят весь train: recall 100% достигается вместе со всеми обычными платежами; "
              "lift к точной доле равен 1. Эти флаги не ранжируют транзакции.",
              "- Сравнение окон относится к уже зафиксированным детекторам. На основании отчёта ничего не перенастроено; "
              "будущие изменения после просмотра меток потребуют отдельной честной валидации.", "",
              "## Качество 117 числовых признаков", "",
              f"- Констант: **{len(quality['constant_columns'])}**; неконстант с доминирующим значением ≥99%: "
              f"**{len(quality['near_constant_columns_99pct'])}**.",
              f"- Групп точных дублей среди неконстант: **{len(quality['nonconstant_duplicate_groups'])}**; "
              f"избыточных неконстантных колонок: **{quality['redundant_nonconstant_columns']}**.",
              f"- После мысленного исключения констант/точных дублей остаётся **{quality['distinct_nonconstant_numeric_columns']}** "
              "различных неконстантных столбцов. Фактический набор из 117 колонок не изменён.",
              f"- NaN: {quality['total_missing_values']}; infinity: {quality['total_infinite_values']}; "
              f"неожиданных отрицательных значений: {quality['total_unexpected_negative_values']}.", "",
              "### Постоянные колонки", ""]
    lines += [f"- `{c}` = {quality['profiles'][c]['dominant_value']:g}" for c in quality["constant_columns"]] or ["Нет."]
    lines += ["", "### Точные дубли неконстантных колонок", ""]
    lines += ["- " + ", ".join(f"`{c}`" for c in group) for group in quality["nonconstant_duplicate_groups"]] or ["Нет."]
    lines += ["", "Дубли определены точным совпадением числовых float64-значений на всех строках train, "
              "с проверкой после хеширования. Это не высокая корреляция и не гарантия совпадения на других выборках. "
              "Константные группы также перечислены в JSON.", "", "### Почти постоянные признаки", "",
              "| Колонка | Доминирующее значение | Доля, % |", "|---|---:|---:|"]
    for name in quality["near_constant_columns_99pct"]:
        p = quality["profiles"][name]
        lines.append(f"| `{name}` | {p['dominant_value']:.6g} | {100*p['dominant_fraction']:.4f} |")
    tail = quality["profiles"]["receiver_future_out_to_payment_ratio_7d"]["overall"]
    lines += ["", "Редкость не означает бесполезность: sparse-флаг scatter-gather 1h входит в почти постоянные, "
              "но именно он показывает наибольшее обогащение положительными примерами в этой диагностике. "
              "Поэтому список ≥99% — повод изучить признаки, а не автоматически удалить их.", "",
              f"Распределения отношений потоков асимметричны: receiver_future_out_to_payment_ratio_7d имеет медиану "
              f"{tail['quantiles']['0.5']:.4f}, p99 {tail['quantiles']['0.99']:.4f}, максимум {tail['max']:.4f}. "
              "Это отношение всего будущего исходящего объёма кошелька к одному платежу; оно может превышать 1 "
              "и не означает, что столько же раз пересланы именно его средства. Данные не обрезались и не преобразовывались.", "",
              "### Распределения всех признаков", "",
              "Для задержек -1 означает отсутствие события/свидетельства, а не отрицательное время. "
              "Медиана ниже включает sentinel; JSON отдельно содержит распределения без него и по двум классам. "
              "Нули в counts/ratios могут означать отсутствие контекста и интерпретируются вместе с count-признаками.", "",
              "| Колонка | Уникальных | Нули, % | -1, % | Медиана | p95 | p99 | Максимум |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, p in quality["profiles"].items():
        stats = p["overall"]
        lines.append(f"| `{name}` | {p['unique_values']:,} | {100*p['zero_fraction']:.2f} | "
                     f"{100*p['minus_one_count']/report['transactions']:.2f} | {stats['quantiles']['0.5']:.6g} | "
                     f"{stats['quantiles']['0.95']:.6g} | {stats['quantiles']['0.99']:.6g} | {stats['max']:.6g} |")
    lines += ["", "## Ограничения и дальнейшие действия", "",
              "Это ретроспективная диагностика полного размеченного train без независимого holdout. "
              "Связанные транзакции и общие сценарии делают наблюдения зависимыми; precision/recall/lift "
              "не являются оценкой качества на новых сценариях. Модель не обучалась, AP не измерялся.", "",
              "Метки существуют только внутри диагностического скрипта: используются для подсчёта TP/FP/FN/TN "
              "и условных распределений, не сохраняются в feature-таблицы. Детекторы, конфигурация, schema и все "
              "сохранённые данные проверены по SHA-256 и не изменены.", "",
              "Перед будущим обучением можно отдельно обсудить исключение констант/дублей и обработку "
              "асимметричных распределений/sentinel, но этот отчёт не удаляет и не преобразует признаки. "
              "Любую полезность признаков необходимо проверять на изолированных fit/holdout графах."]
    return "\n".join(lines) + "\n"


def main() -> None:
    feature_path = output_path("aml_features_v1/train/transactions.parquet")
    schema_path = output_path("aml_features_v1/feature_schema.json")
    label_path = REPO_ROOT / "data/traning_data/train/labels.csv"
    preserved = [feature_path, schema_path, label_path, REPO_ROOT / "feature_workspace/aml_patterns.py",
                 REPO_ROOT / "feature_workspace/prepare_aml_features.py", REPO_ROOT / "feature_workspace/aml_thresholds.json"]
    # Hash all AML artifacts for all splits without analysing validation/test values.
    preserved += [p for p in output_path("aml_features_v1").rglob("*") if p.is_file() and p.suffix in (".json", ".parquet")]
    before = {str(p.relative_to(REPO_ROOT)): sha256(p) for p in preserved}
    features = pd.read_parquet(feature_path)
    columns = json.loads(schema_path.read_text())["numeric_aml_columns"]
    require(len(columns) == 117, "Expected exactly 117 frozen AML numerical features")
    labels = pd.read_csv(label_path, usecols=["TRANSACTION_HASH", "is_suspicious"])
    y = align_targets(features, labels)
    metrics, unions = pattern_metrics(features, y)
    report = {"command": ".venv/bin/python -m feature_workspace.diagnose_aml_train", "scope": "train diagnostics only",
              "transactions": len(features), "positives": int(y.sum()), "negatives": int((y == 0).sum()),
              "exact_prevalence": float(y.mean()), "rounded_reference_prevalence": ROUNDED_PREVALENCE,
              "pattern_metrics": metrics, "union_metrics": unions,
              "feature_quality": profile_features(features, columns, y), "preserved_sha256": before,
              "diagnostic_code_sha256": sha256(Path(__file__)), "detectors_and_data_unchanged": True,
              "labels_used_only_for_diagnostics": True, "model_trained": False}
    require(all(sha256(REPO_ROOT / p) == digest for p, digest in before.items()), "Detector/data input changed")
    directory = REPO_ROOT / "reports"
    (directory / "aml_train_diagnostics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (directory / "aml_train_diagnostics.md").write_text(markdown_report(report))
    for row in metrics:
        print(json.dumps(row))
    q = report["feature_quality"]
    print(json.dumps({k: q[k] for k in ["constant_columns", "nonconstant_duplicate_groups",
                                      "near_constant_columns_99pct", "distinct_nonconstant_numeric_columns"]}))


if __name__ == "__main__":
    main()
