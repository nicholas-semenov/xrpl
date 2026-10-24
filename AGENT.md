# Agent Operating Instructions — Decode & Detect XRPL AML

> **Audience:** Codex and any other coding assistant working in this repository.
> **Purpose:** Keep the implementation goal, source-of-truth rules, execution workflow, and transferable project state consistent across sessions and models.
> **Scope:** Technical implementation only. This document intentionally contains no event logistics or administrative information.

## 1. Your mission

Build a **correct, reproducible, high-performing transaction-level suspicious-payment scoring pipeline** for the synthetic XRP Ledger (XRPL) anti-money-laundering challenge.

- Use the provided labelled training transactions and supporting ledger/transfer/rate data to learn suspicious behaviour.
- Generate **one numeric suspicion score in `[0, 1]` per test `TRANSACTION_HASH`**, with higher scores indicating greater suspicion.
- Optimize ranking quality using **Average Precision (AP)**, not merely binary accuracy or pattern detection counts.
- Use AML patterns, graph structure, timing, amounts, wallet behaviour, and asset conversions as **candidate predictive features**. Detecting a motif does **not** prove that a transaction is suspicious.
- Start with an end-to-end validated baseline; improve it through measured experiments and sound data handling.

Do not confuse the technical objective (ranking individual transactions) with the means of achieving it (graph analysis and AML motif discovery).

## 2. Mandatory reading and authority

**Before inspecting, modifying, or creating implementation code:**

1. Read **`RULES.md` in full**. It is the project's detailed technical specification and the primary source for dataset semantics, feature engineering, AML pattern families, evaluation, validation, output contract, and data-use constraints.
2. Read **`PROGRESS.md`** if it exists. It is the short, persistent handoff record across models and sessions.
3. Inspect the actual repository layout and relevant existing code, tests, configurations, and generated artifacts.
4. Inspect Git status, current branch, upstream and remote configuration; safely pull available remote updates before making code changes (see Git workflow below).
5. Read the dataset's **`README.md`** and bundled helpers (especially `payments.py` and `baseline.py`) *if present*. Verify actual schemas and commands before relying on them.
6. Confirm the next task against what already exists; never blindly repeat completed work from an old plan.

**Naming:** The canonical specification is `RULES.md` (plural). If only `RULE.md` exists, read it and note the naming discrepancy; do not silently pretend that the canonical file was found.

**Instruction priority:** Follow higher-priority system/developer/user instructions. Within the repository, follow explicit, verified dataset semantics and the applicable requirements in `RULES.md`. Treat engineering recommendations in `RULES.md` as recommendations, not mandatory organiser rules. Report contradictions rather than silently picking a convenient interpretation.

**Do not edit `RULES.md` or this instruction file** merely to make existing code appear compliant. Request or explicitly justify any necessary specification change.

## 3. Persistent cross-model memory: `PROGRESS.md`

**You must maintain a root-level file named `PROGRESS.md`.**

- **If it does not exist:** create it immediately after reading `RULES.md`, using the concise template below. Initial status must reflect **verified reality**, not an assumed completed setup.
- **If it exists:** read it at the beginning of every session, compare key claims against the repository, then update it as work proceeds.
- **After every meaningful milestone:** update current status, completed work, measured results, decisions, blockers, and the next 1–3 actions.
- **Before stopping, handing off, or switching models:** refresh it so a new assistant can continue without needing the chat transcript.
- Treat it as a **living snapshot**, not a verbose chronological diary. Consolidate outdated entries; keep it approximately **30–80 lines** where practical. Preserve the latest factual state.
- Include exact relevant file paths and **commands that have actually worked**. For any failed or unrun command, label it accordingly.
- Never invent completed steps, test results, model scores, dataset findings, working commands, or decisions. Mark unverified items as `Not verified` or `Pending`.
- Never store credentials, access tokens, private codes, raw confidential data, or huge terminal logs in `PROGRESS.md`.

### Required `PROGRESS.md` structure

```markdown
# Project Progress — XRPL AML Scoring

## Current status
- Stage: [not started / preprocessing / baseline / features / validation / prediction]
- Current objective: ...
- Last verified working outcome: ...

## Completed and verified
- [item] — [files changed; test or evidence]

## Decisions and assumptions
- [decision] — [why; source if relevant]
- [unverified assumption, explicitly labelled]

## Results and checks
- Validation protocol: [actual split; or not yet established]
- Best validation AP: [number + run ID; or not measured]
- Working commands: [exact commands confirmed to run]

## Git synchronization
- Current branch and upstream: [verified branch/upstream or not configured]
- Last successful pull: [commit/time or not yet performed]
- Last commit and push: [commit hash + remote branch or not yet performed]
- Unpushed changes / Git blockers: [short factual status]

## Blockers / risks
- [problem; effect; what would resolve it]

## Next actions (in priority order)
1. [small, actionable step]
2. [small, actionable step]
3. [optional step]

## Important paths
- [key data/config/code/model/output paths; only if verified]
```

**If a later model takes over:** read `AGENT.md` → `RULES.md` → `PROGRESS.md`, inspect the implementation, verify the recorded state, and continue from the first unfinished priority action. Do not rely on conversational memory as the only record of progress.

## 4. Execution protocol

For each work session:

1. **Orient:** follow the mandatory reading sequence, report any missing critical files, and inspect the current repository state.
2. **Plan briefly:** select the smallest useful next step that improves the runnable end-to-end solution; keep the next tasks in `PROGRESS.md`.
3. **Implement:** make focused, reviewable changes; reuse the supplied helper scripts where valid; avoid speculative rewrites.
4. **Verify:** run the relevant existing tests and/or focused checks. For modelling, report measured validation AP on a genuinely held-out set before claiming improvement.
5. **Record:** update `PROGRESS.md` with actual outputs, limitations, changed paths, and follow-up actions.
6. **Synchronize:** if inside a configured Git repository, commit the verified changes (including `PROGRESS.md`) and push to the configured upstream following Section 5.
7. **Communicate:** summarize what changed, what was verified, Git pull/push status, what remains uncertain, and exactly what should happen next.

Prefer implementation over excessive planning. Do not ask for confirmation when the next safe step is clear. If an essential file is genuinely missing, identify precisely what is needed and continue with independently verifiable work when possible.

## 5. Mandatory Git pull, commit, and push workflow

Treat Git synchronization as part of the working protocol so another model or machine can resume from the repository, **not just the local conversation**. Run these steps whenever Git and a remote are available; do not merely suggest commands.

### At the start of every session, before editing files

1. Inspect the repository with `git status --short --branch`, `git branch --show-current`, and `git remote -v`. Determine the configured upstream with `git rev-parse --abbrev-ref --symbolic-full-name @{upstream}` (this may fail for an untracked branch).
2. If the worktree and index are clean and an upstream exists, run **`git pull --ff-only`** to obtain remote changes. Confirm the result before editing.
3. If local changes are present, **do not overwrite, discard, stash, reset, or blindly pull across them**. Inspect the diff and determine whether they belong to the user or another agent. Preserve them; integrate safely, or record a precise blocker and ask for direction only when necessary.
4. If no Git repository, remote, upstream, network connection, or required credentials are available, record that fact in `PROGRESS.md`; continue with feasible local work. Never claim a pull succeeded unless the Git command did.

### After each meaningful, verified milestone and before handing off

1. Run relevant checks and update `PROGRESS.md` with the *verified* code state, current objective, next steps, and Git synchronization state.
2. Check `git status` and `git diff`. Stage **only intentional project changes**, e.g. `git add path/to/file AGENT.md AGENTS.md PROGRESS.md`; do not automatically use `git add -A` if it risks staging datasets, model artifacts, logs, secrets, credentials, or unrelated user files. Follow `.gitignore`.
3. Make a descriptive commit, such as `git commit -m "Add graph features and validate AML model"`, when there are actual changes to commit. Avoid empty commits or committing unverified claims.
4. **Run `git push`** to the configured upstream after the commit and verify that it succeeded. The goal is to make the latest verified code and progress available to the next agent. If no upstream is configured, do not guess a target branch or publish to an unapproved remote; record the blocker.
5. If the push is rejected because the remote advanced, fetch/inspect remote history. Incorporate those changes safely; do not force-push or rewrite shared history without explicit approval. Re-run affected checks, update `PROGRESS.md`, commit any updates, and retry the push when safe.
6. Keep `PROGRESS.md` accurate about the branch/upstream, latest *verified* Git state and any unresolved synchronization blockers. State the final commit hash and actual pull/push outcome in your session summary, using `git status`/`git log` to verify them. Do not create an infinite series of commits solely to record that the previous push succeeded. If a sync action fails, state the failure clearly; never describe the repository as synchronized.

**Safety:** Never run `git push --force`, destructive `git reset`, `git clean`, unrequested branch deletion, or commands that discard someone's uncommitted changes. Do not push confidential files, dataset dumps, credentials, access tokens, or large generated files unless the repository explicitly requires and permits them. `git pull` / `git push` are expected workflow actions, subject to the environment's permissions and user instructions.

## 6. Technical invariants you must preserve

These are reminders; `RULES.md` gives the full detail.

- **Transaction-level prediction:** exactly one output per test `TRANSACTION_HASH`; transfer legs are not separate labelled transactions.
- **XRPL semantics:** XRP amounts in drops where documented; proper issuer + symbol asset identities; actual delivered/spent amounts rather than treating `SendMax` as cost; avoid double-counting conversion legs and fees.
- **Graph semantics:** represent logical payments, preserve direction, timestamps, transaction identity, and repeated events. Respect temporal ordering in path-based features.
- **Data integrity:** confirm joins, row counts, key uniqueness, missingness, rate conversions, and train/test boundaries on real files.
- **Leakage prevention:** never use target labels as predictive features or improperly fit target-derived statistics on held-out rows. Document whether features use causal history or a permitted full observation window.
- **Modelling:** start with a reproducible baseline; supervised tree models such as CatBoost or LightGBM are recommended options, not mandatory architecture. Add AML motif detectors only when justified by evidence.
- **Evaluation:** compare on a consistent validation protocol using Average Precision as the primary metric. Avoid unsupported performance claims and leaderboard overfitting.
- **Prediction artifact:** exact `TRANSACTION_HASH,score` columns; one row per expected test transaction; finite scores within `[0, 1]`; no missing, duplicate, or extra transaction IDs.
- **Reproducibility:** pinned dependencies or documented versions, deterministic seeds where feasible, working run commands, validation settings, and clear limits on reproducibility.

Use the provided organiser data and approved reference material within the constraints in `RULES.md`. Never seek hidden test labels or use unauthorised outside transaction data.

## 7. Quality standards

- Inspect existing code before editing; follow the repository's conventions and avoid unnecessary dependencies.
- Keep code modular, readable, and testable; separate input parsing, payment reconstruction, feature generation, modelling, validation, and prediction serialization.
- Prefer small, measurable improvements over high-complexity methods that have not been validated.
- Add focused tests for money-unit conversion, issuer identity, payment-leg reconstruction, temporal causality, joins, leakage controls, and prediction-file integrity.
- Do not fabricate column names, file paths, schema facts, test outcomes, AP metrics, or available helpers. Verify them.
- Avoid introducing user secrets into source control, logs, reports, or predictions.
- Do not quietly overwrite working models, valid outputs, or experiments. Preserve a known-good baseline and record meaningful changes.

## 8. Completion standard

A task is complete only when its code/artifacts exist, relevant checks have been run (or failures clearly recorded), `PROGRESS.md` accurately identifies the outcome and next step, and Git changes have been committed and pushed when a configured upstream is accessible (or the precise Git blocker is documented).

The project is technically complete when an independently reproducible pipeline can generate correctly aligned scores for every provided test transaction, with documented, genuinely measured validation AP and verified output checks. Do not claim completion from code alone.
