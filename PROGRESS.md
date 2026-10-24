# Project Progress — XRPL AML Scoring

## Current status
- Stage: Baseline complete / separate feature workspace prepared.
- Current objective: Prepare feature experiments in `feature_workspace/`, keeping original data and the measured baseline intact.
- Last verified working outcome: Separate workspace and bounded output paths created; three path-safety tests passed. Baseline AP remains 0.0835839760.

## Completed and verified
- Read repository instructions and supplied README, `payments.py`, and starter notebook. No separate supplied `baseline.py` exists.
- Initial audit: `scripts/audit_data.py`, `reports/data_audit.md`, `reports/data_audit.json`; all 12 training-package checksums passed.
- Train: 40,131 transactions / 60,557 legs; practice validation: 33,862 / 55,897; test: 40,101 / 65,272. Each split has 151,200 blocks and 700 wallets; wallets/hashes are disjoint across splits.
- Train has 1,250 positives and 38,881 negatives. All supplied payments are successful; audited joins, units, endpoints and rates passed.
- Added `scripts/baseline.py`: supplied helper plus the notebook's 12 features, StandardScaler and balanced L2 logistic regression. No advanced motif detector or alternative estimator added.
- Added pinned `requirements-baseline.txt`, root `README.md`, and measured `reports/baseline_metrics.json` with source/artifact hashes, parameters, coefficients and timings.
- Added six focused tests in `tests/test_baseline.py`; all passed, including parity with supplied notebook functions and leakage/metric checks.
- Model, full split manifest, holdout scores and metrics exist under `outputs/baseline_wallet_seed0/`; generated outputs and `.venv/` are Git-ignored and reproducible.
- CSV coverage/numeric round-trip and saved model prediction round-trip passed. No practice/test predictions produced.
- Added `feature_workspace/` with notebook and ignored generated-output folders, usage instructions and `paths.py`; no features generated or model changes made in this setup.
- Three new tests verify valid destinations and rejection of absolute paths, parent traversal and symlinks into source data.

## Decisions and assumptions
- `RULES.md` is canonical; actual dataset README permits full-window offline investigation. This baseline is not causal/live detection.
- Only labelled train payments, train rates and train annotations are read for this evaluation. Features exclude labels, family/difficulty/group metadata and identifiers.
- Source graph has one connected component over 700 customer wallets. Fixed seed 0 splits sorted wallets 350/350, excludes crossing customer payments, then purges fit rows sharing holdout scenario/cohort IDs.
- Null scenario/cohort values are not treated as a shared group. Group metadata only enforces exclusion or supports post-fit diagnostics, never predictors.
- Fit and holdout features use separately retained payments; all purged payments are excluded from both contexts. Scaler, class weights and coefficients fit on fit rows only.
- Retain exact starter features; stable timestamp/hash tie ordering ensures alignment. Helper-projected VALUE is reference USD, not raw XRP/token VALUE.
- Future feature writers use `feature_workspace.paths.TRAIN_INPUT` for reads and `output_path(...)` for outputs under `feature_workspace/generated/`. Source files and filesystem permissions are unchanged.

## Results and checks
- Validation: one fixed wallet/scenario/cohort-isolated offline holdout, seed 0; no AP-based split/parameter search.
- Fit: 4,949 rows / 169 positives; holdout: 10,112 / 262; purged: 25,070 / 819. Wallet, transaction, non-null scenario and cohort overlap: zero.
- AP: **0.08358397603315604** (`100 × AP = 8.3583976033`), run `starter_logistic_wallet_seed0`; not a test leaderboard score.
- ROC-AUC: **0.734895570969117**; Precision@1%: **0.1568627451**; Recall@1%: **0.0610687023**. Top ceil(1% × 10,112) = 102 contains 16 positives; hash ascending breaks ties.
- Holdout positive share: 2.591%; 10,112 distinct finite scores in [0,1]. Logistic solver converged in 17 iterations.
- Working setup: `python3 -m venv .venv`; `.venv/bin/python -m pip install --no-cache-dir -r requirements-baseline.txt`.
- Working checks: `.venv/bin/python -m pip check`; `.venv/bin/python -m unittest discover -s tests -v` (6 passed).
- Workspace checks: `.venv/bin/python -m unittest discover -s tests -p 'test_feature_workspace.py' -v` (3 passed); `git check-ignore feature_workspace/generated/train_features.parquet` confirmed generated tables are ignored.
- Working run: `.venv/bin/python scripts/baseline.py` (about 2.5 seconds on Apple arm64/macOS 27.0.1, excluding dependency setup).
- Repeat: `.venv/bin/python scripts/baseline.py --output-dir outputs/baseline_repeat --report outputs/baseline_repeat/metrics.json`; exact comparison command is in README and passed.
- Baseline environment: Python 3.10.15; NumPy 2.2.6, pandas 2.3.0, PyArrow 23.0.0, SciPy 1.13.1, scikit-learn 1.7.2; full dependencies pinned, BLAS fitting/prediction threads=1.

## Git synchronization
- Branch/upstream: `master` / `origin/master`; origin `https://github.com/nicholas-semenov/xrpl.git`.
- Last successful pull: 2026-10-24 at `62730a8`, already up to date (previous audit session).
- Current session pull skipped: unrelated tracked `.DS_Store` modification existed at startup and is preserved; no stash/reset/discard performed.
- Last verified commit/push before workspace setup: `11ab9ef` successfully pushed to `origin/master`.
- Workspace, path checks, documentation, ignore rules and progress prepared for commit/push; final hash/outcome reported in session handoff. Existing `.DS_Store` modification is excluded.
- Git metadata/network operations require sandbox escalation; no force-push or destructive operation authorized.

## Blockers / risks
- This is one stress holdout, not an independent complete synthetic week; no confidence interval or fold variability measured.
- Purging removes 62.47% of rows and truncates paths/scenarios. Fit retains no cohort-annotated rows; fit has only 12 hard positives and holdout 17 (159 easy / 86 medium).
- Training/holdout span the same calendar week; future calendar drift and full-world generalization remain untested. AP is not a guaranteed lower bound for leaderboard performance.
- System SciPy 1.15.3 and its fresh wheel failed loading a PROPACK binary on this macOS; isolated SciPy 1.13.1 works. Always use `.venv/bin/python`.
- Practice validation has no labels. README discloses 25 feature-independent ambiguous positives per full split. No hidden-label or external transaction data use.

## Next actions (in priority order)
1. Agree on the first feature definitions; implement them inside `feature_workspace/` with generated outputs kept separate from source data.
2. Preserve the baseline and assess group-safe validation stability/representativeness before comparing feature improvements.
3. Diagnose baseline errors and compare feature additions only through measured ablations; no additional estimator authorized yet.

## Important paths
- `README.md` — exact commands, feature/algorithm explanation, measured results and validation limitations.
- `feature_workspace/README.md`, `feature_workspace/paths.py` — feature workspace and checked output paths; `feature_workspace/generated/` — ignored derived files.
- `scripts/baseline.py`, `tests/test_baseline.py`, `requirements-baseline.txt` — executable baseline and verification.
- `reports/baseline_metrics.json` — canonical measured result, configuration and fingerprints.
- `outputs/baseline_wallet_seed0/` — local split.csv, holdout_predictions.csv, model.joblib, metrics.json (ignored).
- `reports/data_audit.md`, `reports/data_audit.json`, `scripts/audit_data.py` — prior verified audit.
- `data/traning_data/` — supplied training/practice package (on-disk spelling); `data/test_data/` — test inputs, unused in baseline evaluation.
