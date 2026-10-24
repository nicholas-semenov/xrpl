# Project Progress — XRPL AML Scoring

## Current status
- Stage: Features / first four descriptive AML detectors complete; baseline preserved.
- Current objective: Preserve the extended datasets and inspect feature usefulness in a later supervised evaluation; no model training performed in this stage.
- Last verified working outcome: All three datasets extended to 133 columns (original 15 + aml_pattern + 117 numerical features); 36 tests passed in four spawned processes.

## Completed and verified
- Initial audit, canonical transaction preparation and separate directed wallet graphs are preserved; original supplied data checksums still match.
- Canonical inputs: feature_workspace/generated/transaction_tables_v1/{train,validation,test}/ with transactions.parquet and detailed transfer_legs.parquet.
- Graph inputs: feature_workspace/generated/wallet_graphs_v1/{train,validation,test}/ with edges.parquet, nodes.parquet and manifest.json; exact payment IDs/directions/amounts/times retained.
- Added feature_workspace/aml_patterns.py: IDs 1 fan-in, 2 fan-out, 3 scatter-gather, 4 gather-scatter; windows 1h, 24h, 7d and configurable label-free thresholds.
- Added feature_workspace/prepare_aml_features.py; extended transactions saved under generated/aml_features_v1/{train,validation,test}/transactions.parquet, with exact original 15 fields and original row order.
- aml_pattern is a sorted unique list<int8>, allowing multiple IDs or an empty list. Numerical features include per-window counts, distinct counterparties, USD flows, funding/forwarding delays, ratios, compatible paths and witness support.
- feature_schema.json in the generated run lists numerical/categorical model inputs and excluded identifiers/list metadata. All numerical features are finite.
- Added aml_thresholds.json, AML_PATTERNS.md, reports/aml_patterns.{md,json}; reports include counts by window, resource counters, timings, config/code/input/output hashes and interpretation limits.
- Added 10 detector tests in tests/test_aml_patterns.py and scripts/run_tests_parallel.py. Full 36-test suite passed with --workers 4 using multiprocessing spawn.
- Detectors preserve strict time ordering, distinct intermediaries, aggregate funding and deduplicated USD sums. Tests cover boundaries, self-payments, duplicate counterparties, overlapping IDs, annotation neutrality, resource failures and Parquet list round-trips.
- All datasets processed twice with identical saved feature tables; differing pre-existing artifacts are refused. Previous graph/preparation inputs, baseline code/results and source data are unchanged.
- No labels, family, scenario/cohort metadata or external data are detector inputs. No suspicious labels/probabilities or additional ML models were produced.

## Decisions and assumptions
- Full seven-day offline history is permitted by the supplied README; earlier payments may acquire descriptions from later observed events.
- One user payment remains one row/edge. Raw conversion legs and technical liquidity intermediaries are not AML graph hops.
- Default structural thresholds: 3 distinct counterparties/intermediaries; group USD >=100; compatible two-hop leg USD >=10; flow ratio 0.5–1.5. These were fixed without targets or AP tuning.
- Fan witnesses use anchored [T-W,T] deposits/payouts. SG uses distinct S,M,D and strictly ordered S→M→D branches with whole witness span <=W.
- GS uses collection [T-W,C] then redistribution (C,T], with distinct donor/recipient thresholds and aggregate spent/credited flow balance. Individual deposit/payout amounts need not match.
- Each qualifying witness tags participating transactions; final aml_pattern unions all patterns/windows. Support metrics use one deterministic strongest witness, never a fictitious combination.
- Reused event IDs are counted once in USD totals; parallel two-hop event pairs remain separate paths. Equal timestamps cannot establish forwarding order.
- Self-payments remain unchanged but do not supply external motif evidence. Delays use -1 when absent; ratios use zero with count features to identify missing context.
- Original numeric values/types and asset issuer identities are preserved. Generated artifacts remain outside Git; no source data permissions changed.
- For future CatBoost, exclude TRANSACTION_HASH/SENDER/RECEIVER/aml_pattern from predictors; use numerical per-window flags and the explicit feature schema.
- Full-train offline features must be recomputed separately on retained fit/holdout graphs before supervised validation.

## Results and checks
- Transactions / ID1 / ID2 / ID3 / ID4 (union across windows): train 40,131 / 40,131 / 40,131 / 15,607 / 39,800; validation 33,862 / 33,862 / 33,862 / 7,743 / 33,647; test 40,101 / 40,101 / 40,101 / 12,113 / 39,796.
- 1h counts ID1/ID2/ID3/ID4: train 16,011/14,176/326/266; validation 12,447/11,034/282/169; test 15,594/14,896/312/287. Complete window breakdown is in reports/aml_patterns.json.
- Detection runtime per split approximately 16–22 seconds; limits never reached and no sampling/truncation used. Membership counts overlap and are not suspicion metrics.
- Existing graph counts (nodes/edges/directed pairs): train 700/40,131/22,315; validation 700/33,862/18,773; test 700/40,101/22,557. Cross-split wallet/hash intersections remain zero.
- Baseline remains starter_logistic_wallet_seed0: AP 0.0835839760; ROC-AUC 0.7348955710; Precision@1% 0.1568627451; Recall@1% 0.0610687023. No new AP measured.
- Baseline fit/holdout/purged: 4,949/10,112/25,070 transactions with wallet/scenario/cohort isolation; saved model and predictions remain in outputs/baseline_wallet_seed0/.
- Python virtual environment: .venv/; Python 3.10.15 and pinned dependencies in requirements-baseline.txt. Detectors add no dependency or CatBoost installation.
- Working feature command: .venv/bin/python -m feature_workspace.prepare_aml_features.
- Working parallel verification: .venv/bin/python scripts/run_tests_parallel.py --workers 4 (36 passed).
- Prior working commands: .venv/bin/python -m feature_workspace.prepare_transactions; .venv/bin/python -m feature_workspace.build_wallet_graph; .venv/bin/python scripts/baseline.py.

## Git synchronization
- Branch/upstream: master / origin/master; origin https://github.com/nicholas-semenov/xrpl.git.
- Last successful pull: prior audit session, 2026-10-24 at 62730a8 (already up to date).
- Current pull skipped due to pre-existing .DS_Store and data/.DS_Store modifications and untracked feature_workspace/.DS_Store. All preserved and excluded.
- Last verified commit/push before detectors: 9faef27 successfully pushed to origin/master.
- Detector code/config, multiprocessing runner, tests, reports, documentation and progress prepared for commit/push; final hash/outcome reported in session handoff. No destructive Git action used.

## Blockers / risks
- Seven-day fan-in/fan-out flags saturate every transaction at these broad defaults; they are constant descriptions, not evidence that all activity is suspicious. Short-window and continuous features vary.
- GS is also broad over 7d. Supervised usefulness, precision/recall and AP contribution are unmeasured; do not equate motif membership with suspicious classification.
- Flow-ratio checks use all events in an anchored window, so larger-window flags need not contain smaller-window flags; final membership unions them.
- Budget limits fail loudly rather than return partial detections. Existing baseline is a single heavily purged stress holdout; independent-world generalization remains unmeasured.
- System SciPy 1.15.3 fails on this macOS; the pinned isolated SciPy 1.13.1 works. Always use .venv/bin/python.

## Next actions (in priority order)
1. Inspect the extended schema and short-window feature distributions; preserve current descriptive thresholds and reproducibility artifacts.
2. Recompute features on isolated fit/holdout graphs before any future supervised experiment.
3. Measure feature ablations in a separately authorized modelling task; no model trained for these features yet.

## Important paths
- feature_workspace/aml_patterns.py, feature_workspace/prepare_aml_features.py, feature_workspace/aml_thresholds.json — detector logic/configuration.
- feature_workspace/AML_PATTERNS.md, reports/aml_patterns.{md,json} — exact definitions, commands, counts and limits.
- feature_workspace/generated/aml_features_v1/ — ignored extended tables, feature_schema.json and summary.json.
- scripts/run_tests_parallel.py, tests/test_aml_patterns.py — multiprocessing test runner and detector tests.
- feature_workspace/generated/{transaction_tables_v1,wallet_graphs_v1}/ — preserved canonical/graph inputs.
- scripts/baseline.py, reports/baseline_metrics.json, outputs/baseline_wallet_seed0/ — preserved measured baseline.
