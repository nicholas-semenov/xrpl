# Project Progress — XRPL AML Scoring

## Current status
- Stage: Features / labelled train diagnostics of frozen AML detectors complete.
- Current objective: Preserve diagnostic findings without changing thresholds, detectors, feature tables or models.
- Last verified working outcome: 12 pattern/window metrics plus 4 unions and all 117 feature distributions audited; 41 tests passed in four spawned processes.

## Completed and verified
- Prior audits, canonical transaction tables, wallet graphs and first-four-pattern datasets remain unchanged.
- Canonical transactions: 15 fields, exact original IDs/order; raw detailed legs preserved under generated/transaction_tables_v1/{train,validation,test}/.
- Directed multigraphs: one actual SENDER→RECEIVER payment per hash, parallel payments retained; stored under generated/wallet_graphs_v1/{split}/.
- AML feature stage: IDs 1 fan-in, 2 fan-out, 3 scatter-gather, 4 gather-scatter; fixed windows 1h/24h/7d and configurable descriptive thresholds.
- Extended tables remain under generated/aml_features_v1/{split}/transactions.parquet with original 15 fields, list<int8> aml_pattern and 117 numerical columns (133 total). Schema and dataset artifacts are unmodified.
- Added feature_workspace/diagnose_aml_train.py: one-to-one labels.csv join by hash, only is_suspicious read; no family/difficulty/scenario/cohort annotation use.
- Added reports/aml_train_diagnostics.md and .json with counts, TP/FP/FN/TN, precision/recall, two lift normalizations, quantiles, class-conditional diagnostics, sentinels, constants and exact duplicate groups.
- Added five diagnostic tests in tests/test_aml_diagnostics.py; full suite is 41 passing tests using scripts/run_tests_parallel.py --workers 4.
- Diagnostic metrics and exact duplicates verified against hand-built examples; original data and detector files checked by SHA-256. No ML model was trained.

## Decisions and assumptions
- All labelled measurements use full train only, not an independent holdout; targets are diagnostic inputs only and never written to feature tables.
- TP means any is_suspicious=1 payment, not proof that the detector identified the correct annotated typology.
- User-specified lift baseline is 3.11%; report also gives exact prevalence 1250/40131 = 3.1147990332%, preventing rounding from making all-positive flags appear enriched.
- Precision/lift for zero detections are null; recall denominator is all 1,250 positives. Pattern overlaps and window unions are not additive.
- Exact duplicate comparison uses all train rows and numeric float64 values, with hash matches confirmed by full comparison; integer precision is guarded. High correlation alone is not a duplicate.
- Near-constant means a nonconstant column with one value in >=99% of rows. Sparse informative flags must not be deleted solely for rarity.
- Delay -1 is an absence sentinel; report includes overall and sentinel-excluded distributions. Zero ratios require count context, not an invented missing price.
- Detector thresholds remain fixed: 3 distinct counterparties/intermediaries; group USD >=100; compatible leg USD >=10; flow ratio 0.5–1.5.
- Full seven-day offline context is permitted. Strict forwarding time, distinct SG intermediaries, deduplicated flow sums and separate split graphs remain preserved.
- Full-train AML features must be recomputed on retained isolated fit/holdout graphs before future supervised evaluation.

## Results and checks
- Train: 40,131 transactions, 1,250 positives, 38,881 negatives. Labels cover exactly the saved transaction hashes with no duplicate keys.
- Fan-in precision/recall/lift-exact: 1h 3.3477%/42.88%/1.0748; 24h 3.1136%/99.84%/0.9996; 7d 3.1148%/100%/1.0.
- Fan-out precision/recall/lift-exact: 1h 4.2113%/47.76%/1.3520; 24h 3.1161%/100%/1.0004; 7d 3.1148%/100%/1.0.
- Scatter-gather: 1h 326 found, 254 TP/72 FP, precision 77.9141%, recall 20.32%, lift 25.0528 vs 3.11% / 25.0142 vs exact; 24h precision 47.3851%, recall 23.92%, lift-exact 15.2129; 7d precision 4.2751%, recall 53.36%, lift-exact 1.3725.
- Gather-scatter: 1h 266 found, 13 TP, precision 4.8872%, recall 1.04%, lift-exact 1.5690; 24h lift-exact 1.0109; 7d lift-exact 1.0073. Complete counts and unions are in the diagnostic reports.
- Feature audit: 2 constants (fan_in_7d_detected, fan_out_7d_detected), both 1; 14 near-constant nonconstants; 2 nonconstant duplicate groups, each path_count = intermediary_count for SG 1h/24h on train.
- 113 distinct nonconstant numeric columns after conceptual exclusion of constants/duplicates; no columns actually removed. NaN/infinity/unexpected negative counts all zero.
- Heavy-tail example: receiver_future_out_to_payment_ratio_7d median 36.6738, p99 1727.5293, max 16822.0878; these are context ratios, not attribution of specific funds.
- Existing detector memberships (ID1/2/3/4 union): train 40,131/40,131/15,607/39,800; validation 33,862/33,862/7,743/33,647; test 40,101/40,101/12,113/39,796.
- Baseline remains AP 0.0835839760, ROC-AUC 0.7348955710, Precision@1% 0.1568627451, Recall@1% 0.0610687023 on its isolated holdout. No new AP measured.
- Environment: .venv/, Python 3.10.15, dependencies pinned in requirements-baseline.txt; no dependency added.
- Working diagnostics: .venv/bin/python -m feature_workspace.diagnose_aml_train.
- Working multiprocessing tests: .venv/bin/python scripts/run_tests_parallel.py --workers 4 (41 passed).
- Prior reproduction: .venv/bin/python -m feature_workspace.prepare_aml_features; .venv/bin/python -m feature_workspace.build_wallet_graph; .venv/bin/python -m feature_workspace.prepare_transactions.

## Git synchronization
- Branch/upstream: master / origin/master; origin https://github.com/nicholas-semenov/xrpl.git.
- Last successful pull: prior audit session, 2026-10-24 at 62730a8 (already up to date).
- Current pull skipped due to pre-existing .DS_Store and data/.DS_Store modifications and untracked feature_workspace/.DS_Store; all preserved and excluded.
- Last verified commit/push before diagnostics: 93bb407 successfully pushed to origin/master.
- Diagnostic module, tests, two reports, README and progress prepared for commit/push; final hash/outcome reported in session handoff. No destructive Git operation used.

## Blockers / risks
- No train diagnostic is an independent generalization estimate; transactions/scenarios are dependent. Reviewing targets can bias future decisions, so subsequent changes require honest held-out evaluation.
- Seven-day fan-in/out flags are constant; long-window GS provides little enrichment. Short-window SG is promising on train but its held-out contribution is unmeasured.
- Duplicate equality is observed on train only, not guaranteed on unseen histories. Rare flags can be highly informative, so near-constant is not a deletion rule.
- No threshold, feature selection, clipping or normalization was applied. Existing stress holdout remains heavily purged; full-world generalization unmeasured.
- Always use .venv/bin/python; system SciPy 1.15.3 fails on this macOS while pinned isolated SciPy 1.13.1 works.

## Next actions (in priority order)
1. Review the train diagnostic report; preserve frozen detectors and extended datasets.
2. Separately decide whether to exclude constants/duplicate columns, validating schema stability before any future modelling.
3. Recompute features on isolated graph contexts and measure held-out feature contribution only in a separately authorized modelling task.

## Important paths
- feature_workspace/diagnose_aml_train.py; reports/aml_train_diagnostics.{md,json}; tests/test_aml_diagnostics.py — read-only labelled diagnostics.
- feature_workspace/aml_patterns.py; aml_thresholds.json; AML_PATTERNS.md — frozen detector definitions and thresholds.
- feature_workspace/generated/aml_features_v1/ — unchanged extended datasets, feature_schema.json and summary.json.
- scripts/run_tests_parallel.py — spawned multiprocessing test runner.
- feature_workspace/generated/{transaction_tables_v1,wallet_graphs_v1}/ — preserved canonical and graph inputs.
- scripts/baseline.py; reports/baseline_metrics.json; outputs/baseline_wallet_seed0/ — preserved measured baseline.
