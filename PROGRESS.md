# Project Progress — XRPL AML Scoring

## Current status
- Stage: Features / wallet transaction graph foundation complete; baseline preserved.
- Current objective: Preserve verified split-specific graphs for subsequent AML feature work; no pattern detectors or model training in this milestone.
- Last verified working outcome: Three lossless directed wallet multigraphs generated and reconstructed deterministically; all 26 tests passed.

## Completed and verified
- Read repository instructions, supplied README, payments.py and starter notebook; no separate supplied baseline.py exists.
- Initial audit: scripts/audit_data.py and reports/data_audit.{md,json}; all 12 supplied training-package checksums passed.
- Train: 40,131 transactions / 60,557 raw legs; validation: 33,862 / 55,897; test: 40,101 / 65,272. Each split contains 700 wallets with disjoint addresses/hashes across splits.
- Starter logistic baseline implemented in scripts/baseline.py; pinned environment, tests, commands and real metrics are recorded in README.md and reports/baseline_metrics.json.
- Canonical preparation: feature_workspace/prepare_transactions.py generates all 15 fields and separately preserves detailed legs under generated/transaction_tables_v1/{split}/. The unused notebooks/ directory was removed.
- Preparation checks pass for joins, ordered leg paths, issuer identity, normalized units, fees, hourly rates, hashes and Parquet round-trips. Every destination USD amount matches supplied payments.py.
- Graph implementation: feature_workspace/build_wallet_graph.py provides build_wallet_graph(), load_wallet_graph(), WalletGraph.incoming()/outgoing(), split guards and statistics.
- Generated edges.parquet, nodes.parquet and manifest.json under feature_workspace/generated/wallet_graphs_v1/{train,validation,test}/; all 15 prepared edge attributes retained exactly.
- reports/wallet_graphs.{md,json} and generated/wallet_graphs_v1/summary.json contain measured degrees, volumes, count distributions, provenance, hashes and validation results.
- Eight graph tests added in tests/test_wallet_graph.py. Full suite: 26 tests passed, covering parallel/reverse/self edges, sink wallets, exact attributes, temporal adjacency, labels, split separation, original records and reload corruption.
- Graphs rebuilt identically from shuffled inputs, reloaded losslessly and rerun with existing artifacts. Original transaction and all prior preparation artifact hashes remain unchanged.
- No AML detectors, pattern IDs, label-derived graph inputs or new ML models added. Existing baseline code, scores and model artifacts are preserved.

## Decisions and assumptions
- Actual dataset README permits full seven-day offline graph context; future-within-window activity is not a causal live-detection benchmark.
- One graph edge is one actual customer payment SENDER → RECEIVER, keyed by TRANSACTION_HASH; repeated pairs are separate edges.
- Only prepared transaction tables construct the graphs. Original transaction columns are read separately to validate coverage/direction/time; labels and raw conversion legs are not parsed for graph construction.
- Nodes are unique payment endpoints; conversion legs/intermediary counts never create extra graph nodes/edges or imply AML layering.
- Edges and adjacency are ordered by TIMESTAMP, then hash. Equal timestamps have deterministic ordering only; a strictly later hop requires a greater timestamp.
- IN_DEGREE/OUT_DEGREE count transaction edges; UNIQUE_IN/OUT_NEIGHBORS count counterparties. TRANSACTION_COUNT counts distinct incident hashes, with self-loops counted once.
- Incoming USD sums DESTINATION_AMOUNT_USD; outgoing USD sums SOURCE_AMOUNT_USD. Conversion valuations can differ; fees remain separate XRP attributes.
- Raw/processed data remain inputs; generated outputs use checked paths in feature_workspace/paths.py. Differing existing graph artifacts are refused; choose a new --run-name for changed definitions.
- Full train graph statistics must not be reused across supervised fit/holdout boundaries; rebuild graph contexts separately from retained subsets.
- Source/destination amounts use actual first/last executed VALUE after unit checks, not SendMax or summed conversion-leg values. Assets retain issuer identity.

## Results and checks
- Graph counts (nodes / edges / directed wallet pairs): train 700 / 40,131 / 22,315; validation 700 / 33,862 / 18,773; test 700 / 40,101 / 22,557.
- Each graph: 676 unique senders, 700 unique receivers, 676 wallets with both directions, 24 incoming-only wallets; zero self-loops and zero cross-split wallet/hash intersections.
- Incoming/outgoing USD totals: train 5,677,308.097102 / 5,684,000.818105; validation 5,202,975.393174 / 5,215,014.360740; test 5,580,437.289433 / 5,591,795.039585.
- Mean in/out transaction degree: train 57.3300; validation 48.3743; test 57.2871. Exact histograms and min/median/percentile/max statistics are in graph reports.
- Conversion transactions / actual steps: train 16,450 / 20,426; validation 17,798 / 22,035; test 20,261 / 25,171. Prior preparation reports are unchanged.
- Baseline validation: seed 0 wallet split plus scenario/cohort purging; fit 4,949 / 169 positives; holdout 10,112 / 262; purged 25,070 / 819; no shared wallet/hash/group identities.
- Baseline AP 0.08358397603315604 (100×AP 8.3583976033); ROC-AUC 0.734895570969117; Precision@1% 0.1568627451; Recall@1% 0.0610687023 (16 positives in top 102). No new AP measured.
- Environment: Python 3.10.15; NumPy 2.2.6, pandas 2.3.0, PyArrow 23.0.0, SciPy 1.13.1, scikit-learn 1.7.2. Full dependencies pinned in requirements-baseline.txt; graphs add no dependency.
- Working setup: python3 -m venv .venv; .venv/bin/python -m pip install --no-cache-dir -r requirements-baseline.txt.
- Working graph command: .venv/bin/python -m feature_workspace.build_wallet_graph.
- Working verification: .venv/bin/python -m unittest discover -s tests -v (26 passed).
- Working preparation: .venv/bin/python -m feature_workspace.prepare_transactions.
- Working baseline: .venv/bin/python scripts/baseline.py; repeat/score comparison commands remain in README.md.

## Git synchronization
- Branch/upstream: master / origin/master; origin https://github.com/nicholas-semenov/xrpl.git.
- Last successful pull: 2026-10-24 at 62730a8, already up to date (prior audit session).
- Current session pull skipped because pre-existing tracked .DS_Store and data/.DS_Store modifications plus untracked feature_workspace/.DS_Store were present; all preserved and excluded.
- Last verified commit/push before graph work: 4b4e41e successfully pushed to origin/master.
- Graph code, tests, reports, documentation and progress prepared for commit/push; final commit hash and actual outcome reported in session handoff.
- No stash/reset/discard/force-push used. Git metadata/network writes require sandbox escalation.

## Blockers / risks
- No graph integrity issue found. Hash tie ordering does not establish temporal causality for equal-time events.
- Full-week graph statistics describe supplied synthetic histories; future supervised validation must preserve fit/holdout isolation.
- Existing baseline is one stress holdout, purging 62.47% of rows and truncating scenarios; fit has 12 hard positives and holdout 17. No independent-world labelled validation or fold uncertainty measured.
- System SciPy 1.15.3 fails loading a binary on this macOS; isolated SciPy 1.13.1 works. Use .venv/bin/python.
- Practice validation has no labels; supplied README discloses 25 feature-independent ambiguous positives per full split.

## Next actions (in priority order)
1. Use the verified graph/adjacency API for a separately authorized AML feature milestone; preserve transaction identity, direction and strict temporal ordering.
2. Rebuild isolated fit/holdout graph contexts before any supervised feature evaluation; assess validation representativeness.
3. Compare feature contributions through measured ablations only when model evaluation is requested; no detector or new estimator implemented yet.

## Important paths
- feature_workspace/build_wallet_graph.py, tests/test_wallet_graph.py — graph implementation and focused tests.
- feature_workspace/generated/wallet_graphs_v1/ — ignored lossless graph tables, manifests and summary.
- reports/wallet_graphs.md, reports/wallet_graphs.json — graph statistics and reproducibility evidence.
- feature_workspace/README.md, README.md — schema, definitions, API and exact commands.
- feature_workspace/generated/transaction_tables_v1/, reports/transaction_preparation.{md,json} — preserved canonical inputs and detailed legs.
- scripts/baseline.py, reports/baseline_metrics.json, outputs/baseline_wallet_seed0/ — preserved measured baseline.
