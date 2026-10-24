# Project Progress — XRPL AML Scoring

## Current status
- Stage: Preprocessing / transaction-level feature tables complete; baseline preserved.
- Current objective: Use verified transaction tables for subsequent feature work while preserving split isolation and original data.
- Last verified working outcome: All 15 requested fields generated for train/validation/test, detailed legs retained separately, conversion reports saved; 18 tests passed. Baseline AP remains 0.0835839760.

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
- Added `feature_workspace/` with ignored generated-output folder and checked paths. Removed the unused empty `notebooks/` directory at the user's request.
- Three new tests verify valid destinations and rejection of absolute paths, parent traversal and symlinks into source data.
- Added `feature_workspace/prepare_transactions.py` and nine tests: first/last executed amounts, issuer identity, UTC hourly rates, actual asset changes, safe joins and artifact preservation.
- Produced `generated/transaction_tables_v1/{train,validation,test}/transactions.parquet` (15 columns, exact original transaction order) and `transfer_legs.parquet` (all original columns/types, sorted legs).
- `reports/transaction_preparation.md` / `.json` contain split summaries, conversion distributions, top asset pairs and 12 sample calculations. All destination USD amounts match supplied `payments.py`.
- Every input used in preparation has unchanged SHA-256; all 12 supplied training-package checksums still match. Output Parquet round-trips passed. Labels were not read; no model retrained.

## Decisions and assumptions
- `RULES.md` is canonical; actual dataset README permits full-window offline investigation. This baseline is not causal/live detection.
- Baseline evaluation uses only labelled train inputs. New transaction preparation independently reads all three splits without labels or annotations; identifiers remain alignment fields, not model features.
- Source graph has one connected component over 700 customer wallets. Fixed seed 0 splits sorted wallets 350/350, excludes crossing customer payments, then purges fit rows sharing holdout scenario/cohort IDs.
- Null scenario/cohort values are not treated as a shared group. Group metadata only enforces exclusion or supports post-fit diagnostics, never predictors.
- Fit and holdout features use separately retained payments; all purged payments are excluded from both contexts. Scaler, class weights and coefficients fit on fit rows only.
- Retain exact starter features; stable timestamp/hash tie ordering ensures alignment. Helper-projected VALUE is reference USD, not raw XRP/token VALUE.
- Future feature writers use `feature_workspace.paths.TRAIN_INPUT` for reads and `output_path(...)` for outputs under `feature_workspace/generated/`. Source files and filesystem permissions are unchanged.
- Canonical source/destination amounts come from normalized VALUE after validating SOURCE_VALUE units. Prices match full asset identity and containing UTC hour independently; SendMax and summed leg values are never transaction spending.
- Conversion steps count adjacent issuer+symbol changes, not extra legs; intermediaries count distinct execution-path addresses excluding sender/receiver. These are liquidity providers in supplied conversions, not AML hops.

## Results and checks
- Validation: one fixed wallet/scenario/cohort-isolated offline holdout, seed 0; no AP-based split/parameter search.
- Fit: 4,949 rows / 169 positives; holdout: 10,112 / 262; purged: 25,070 / 819. Wallet, transaction, non-null scenario and cohort overlap: zero.
- AP: **0.08358397603315604** (`100 × AP = 8.3583976033`), run `starter_logistic_wallet_seed0`; not a test leaderboard score.
- ROC-AUC: **0.734895570969117**; Precision@1%: **0.1568627451**; Recall@1%: **0.0610687023**. Top ceil(1% × 10,112) = 102 contains 16 positives; hash ascending breaks ties.
- Holdout positive share: 2.591%; 10,112 distinct finite scores in [0,1]. Logistic solver converged in 17 iterations.
- Working setup: `python3 -m venv .venv`; `.venv/bin/python -m pip install --no-cache-dir -r requirements-baseline.txt`.
- Working checks: `.venv/bin/python -m pip check`; `.venv/bin/python -m unittest discover -s tests -v` (18 passed after transaction preparation).
- Workspace checks: `.venv/bin/python -m unittest discover -s tests -p 'test_feature_workspace.py' -v` (3 passed); `git check-ignore feature_workspace/generated/train_features.parquet` confirmed generated tables are ignored.
- Working run: `.venv/bin/python scripts/baseline.py` (about 2.5 seconds on Apple arm64/macOS 27.0.1, excluding dependency setup).
- Repeat: `.venv/bin/python scripts/baseline.py --output-dir outputs/baseline_repeat --report outputs/baseline_repeat/metrics.json`; exact comparison command is in README and passed.
- Baseline environment: Python 3.10.15; NumPy 2.2.6, pandas 2.3.0, PyArrow 23.0.0, SciPy 1.13.1, scikit-learn 1.7.2; full dependencies pinned, BLAS fitting/prediction threads=1.
- Preparation command: `.venv/bin/python -m feature_workspace.prepare_transactions`; repeated successfully with existing identical artifacts. Different content is refused; change `--run-name` for changed definitions.
- Conversion counts (transactions / actual steps / percentage): train 16,450 / 20,426 / 40.9908%; validation 17,798 / 22,035 / 52.5604%; test 20,261 / 25,171 / 50.5249%.
- Step distributions 0/1/2: train 23,681/12,474/3,976; validation 16,064/13,561/4,237; test 19,840/15,351/4,910. No missing endpoint prices or null canonical values.

## Git synchronization
- Branch/upstream: `master` / `origin/master`; origin `https://github.com/nicholas-semenov/xrpl.git`.
- Last successful pull: 2026-10-24 at `62730a8`, already up to date (previous audit session).
- Current session pull skipped: unrelated tracked `.DS_Store` modification existed at startup and is preserved; no stash/reset/discard performed.
- Last verified commit/push before transaction preparation: `486126e` successfully pushed to `origin/master`.
- Preparation module, tests, reports, notebook-folder removal, documentation and progress prepared for commit/push; final hash/outcome reported in session handoff. Existing `.DS_Store` modification is excluded.
- Git metadata/network operations require sandbox escalation; no force-push or destructive operation authorized.

## Blockers / risks
- This is one stress holdout, not an independent complete synthetic week; no confidence interval or fold variability measured.
- Purging removes 62.47% of rows and truncates paths/scenarios. Fit retains no cohort-annotated rows; fit has only 12 hard positives and holdout 17 (159 easy / 86 medium).
- Training/holdout span the same calendar week; future calendar drift and full-world generalization remain untested. AP is not a guaranteed lower bound for leaderboard performance.
- System SciPy 1.15.3 and its fresh wheel failed loading a PROPACK binary on this macOS; isolated SciPy 1.13.1 works. Always use `.venv/bin/python`.
- Practice validation has no labels. README discloses 25 feature-independent ambiguous positives per full split. No hidden-label or external transaction data use.

## Next actions (in priority order)
1. Use verified canonical transaction fields for the next feature milestone; preserve original data, raw legs and baseline artifacts.
2. Apply baseline fit/holdout isolation before computing future wallet histories; assess validation representativeness before comparing feature improvements.
3. Evaluate feature contributions only through measured ablations in a subsequent modelling task; no additional estimator authorized yet.

## Important paths
- `README.md` — exact commands, feature/algorithm explanation, measured results and validation limitations.
- `feature_workspace/README.md`, `feature_workspace/paths.py` — feature workspace and checked output paths; `feature_workspace/generated/` — ignored derived files.
- `feature_workspace/prepare_transactions.py`, `reports/transaction_preparation.md`, `reports/transaction_preparation.json` — canonical preparation and conversion findings.
- `scripts/baseline.py`, `tests/test_baseline.py`, `requirements-baseline.txt` — executable baseline and verification.
- `reports/baseline_metrics.json` — canonical measured result, configuration and fingerprints.
- `outputs/baseline_wallet_seed0/` — local split.csv, holdout_predictions.csv, model.joblib, metrics.json (ignored).
- `reports/data_audit.md`, `reports/data_audit.json`, `scripts/audit_data.py` — prior verified audit.
- `data/traning_data/` — supplied training/practice package (on-disk spelling); `data/test_data/` — test inputs, unused in baseline evaluation.
