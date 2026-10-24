# Project Progress — XRPL AML Scoring

## Current status
- Stage: Not started / repository instructions read; dataset inspection pending.
- Current objective: Inspect the supplied data and code, verify schemas, and establish a reproducible baseline.
- Last verified working outcome: Read the repository instructions and inspected Git; no implementation or model results verified.

## Completed and verified
- Read `AGENTS.md`, `AGENT.md`, `RULES.md`, and this progress file in full.
- Verified tracked data directories: `data/traning_data/` and `data/test_data/`; schemas and helpers remain uninspected.
- No implementation steps, tests, or model results have been verified.

## Decisions and assumptions
- `RULES.md` is the canonical technical specification; `AGENT.md` defines the workflow.
- Suspicion scoring is at the transaction level; Average Precision is the primary ranking metric.
- Dataset columns, helper behaviour and actual results are not yet verified in this project workspace.

## Results and checks
- Validation protocol: Not established.
- Best validation AP: Not measured.
- Working commands: `git status --short --branch`, `git branch --show-current`, `git remote -v`, `git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'`, `git log -1 --oneline`, `git ls-files`.

## Git synchronization
- Current branch and upstream: `master` tracking `origin/master`; origin is `https://github.com/nicholas-semenov/xrpl.git`.
- Last successful pull: Not performed; skipped because `AGENT.md`, `AGENTS.md`, and `PROGRESS.md` were untracked.
- Last commit and push: Starting HEAD `168db09` (`md`); prior push not verified. Instruction-file commit and push requested by user; outcome pending.
- Unpushed changes / Git blockers: Only the three instruction/progress files are pending; no tracked-file changes at startup. No `.gitignore` exists. Stage only those three files.

## Blockers / risks
- Actual dataset and repository contents must be inspected before implementation assumptions are made.

## Next actions (in priority order)
1. Finish the requested instruction-file commit/push, then inspect repository structure and dataset `README.md` before implementation.
2. Audit the actual training/test tables, `TRANSACTION_HASH` integrity, XRPL money units, transfer legs and available helper scripts.
3. Implement or run a verified baseline, establish holdout validation, and record actual Average Precision.

## Important paths
- `AGENT.md` — agent workflow and cross-model handoff instructions.
- `AGENTS.md` — Codex auto-discovery entry point.
- `RULES.md` — project technical requirements and recommendations.
- `PROGRESS.md` — this compact, continuously updated handoff snapshot.
- Git workflow — pull safely before editing; commit and push verified milestones when an upstream is configured.
