# Project Progress — XRPL AML Scoring

## Current status
- Stage: Preprocessing / initial dataset audit complete.
- Current objective: Establish a reproducible baseline with held-out Average Precision.
- Last verified working outcome: All three supplied splits audited; joins, units, prices, payment projection, label coverage and split separation passed checks.

## Completed and verified
- Read `AGENTS.md`, `AGENT.md`, `RULES.md`, and this progress file in full.
- Read `data/traning_data/README.md`, `payments.py`, and all starter notebook cells; no `baseline.py` supplied.
- Added `scripts/audit_data.py`; successful run writes exact schemas, nulls, label summaries and integrity results to `reports/data_audit.json`.
- Added human-readable findings and run instructions in `reports/data_audit.md`.
- Added `.gitignore` entries for generated Python bytecode caches.
- Train: 40,131 transactions / 60,557 legs; practice validation: 33,862 / 55,897; test: 40,101 / 65,272. Each split has 151,200 blocks and 700 wallets.
- Train has 1,250 positives (3.115%) and 38,881 negatives; difficulty counts among positives: 800 easy, 225 medium, 225 hard.
- All 12 supplied training-package checksums match. No wallet/hash overlap between splits; no missing leg prices or failed integrity assertions.
- Bundled payment helper executed on every split and verified against delivered amounts and reference rates. Notebook not executed; no model trained.

## Decisions and assumptions
- `RULES.md` is the canonical technical specification; `AGENT.md` defines the workflow.
- Suspicion scoring is at the transaction level; Average Precision is the primary ranking metric.
- Actual dataset README permits whole-window offline features; keep each synthetic world's graph separate.
- Exclude `family`, `difficulty`, `scenario_id`, `cohort_id` and raw identifiers from predictors; annotation metadata may support diagnostics/evaluation grouping.
- Use issuer + symbol asset identity and the first executed leg for actual spent amounts. Helper-projected `VALUE` is USD, unlike raw leg `VALUE`.
- Keep the strict two-column prediction contract in `RULES.md`; README also permits an optional reason column, which is unnecessary.

## Results and checks
- Validation protocol: Not established. Starter uses stratified 20% holdout, seed 0; add a stronger graph/scenario generalization check when modelling.
- Best validation AP: Not measured.
- Working commands: `python3 scripts/audit_data.py`; `git status --short --branch`; `git pull --ff-only`; `git push`.
- Audit environment: Python 3.10.15; pandas 2.3.0; NumPy 2.2.6; PyArrow 23.0.0. Python assertions must remain enabled.

## Git synchronization
- Current branch and upstream: `master` tracking `origin/master`; origin is `https://github.com/nicholas-semenov/xrpl.git`.
- Last successful pull: 2026-10-24, `git pull --ff-only` reported already up to date at `62730a8`.
- Last commit and push: `62730a8` successfully pushed to `origin/master` before this audit. Audit changes are prepared for the next commit/push.
- Unpushed changes / Git blockers: Audit script, reports, cache ignores and progress update prepared for commit. An unrelated tracked `.DS_Store` changed during the session; preserve and exclude it. Sandbox requires escalation for Git metadata/network writes.

## Blockers / risks
- Practice validation has no labels; local AP must come from held-out train data.
- README discloses 25 ambiguous hard positives with feature-independent labels; avoid claiming all positives are identifiable.
- Conversion share differs: train 40.99%, practice validation 52.56%, test 50.52%; issuer addresses and wallets differ across splits.
- Random transaction splitting can share graph/scenario context and overstate generalization. No validation AP measured yet.

## Next actions (in priority order)
1. Run an adapted reproducible starter baseline; measure AP on held-out train labels and record the split/configuration.
2. Establish a stronger time/group/scenario generalization check compatible with permitted offline features.
3. Compare wallet/temporal feature additions through measured ablations before selecting a final predictor.

## Important paths
- `AGENT.md` — agent workflow and cross-model handoff instructions.
- `AGENTS.md` — Codex auto-discovery entry point.
- `RULES.md` — project technical requirements and recommendations.
- `PROGRESS.md` — this compact, continuously updated handoff snapshot.
- `reports/data_audit.md`, `reports/data_audit.json` — verified dataset findings and full machine-readable details.
- `scripts/audit_data.py` — reproducible audit; uses the supplied `data/traning_data/payments.py`.
- Git workflow — pull safely before editing; commit and push verified milestones when an upstream is configured.
