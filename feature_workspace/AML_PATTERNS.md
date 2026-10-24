# First four AML motif descriptions

These are configurable descriptions of observable topology, timing and reference-USD flows. They are not ground-truth classes, suspicion decisions or calibrated probabilities. Benign hubs, commerce and treasury flows can satisfy the same definitions. No labels, family, difficulty, scenario/cohort metadata, external data or learned thresholds are used.

## Reproduce

Use the existing pinned environment from `requirements-baseline.txt`, then run from the repository root:

```sh
.venv/bin/python scripts/run_tests_parallel.py --workers 4
.venv/bin/python -m feature_workspace.prepare_aml_features
```

The test runner uses `multiprocessing` with spawned worker processes, up to four test modules concurrently. It reports failures separately and returns nonzero if any module fails. Detector processing is deterministic and applied separately to each graph.

Inputs: `generated/wallet_graphs_v1/{train,validation,test}/` and the corresponding canonical transaction tables, used to preserve original row order. Graph identities are checked for split separation. Existing graph and transaction artifacts are fingerprinted before/after. The pipeline never opens `labels.csv` or ground-truth annotation files.

Outputs: `generated/aml_features_v1/{train,validation,test}/transactions.parquet`, plus `feature_schema.json` and `summary.json` in the run directory. Aggregate counts and provenance are published in `../reports/aml_patterns.md` / `.json`. Full generated tables are ignored by Git. Existing differing tables are refused; choose `--run-name aml_features_v2` when changing feature definitions or thresholds.

## Fixed windows and configurable thresholds

Windows are 3,600 seconds (1h), 86,400 seconds (24h), and 604,800 seconds (7d). Every qualifying motif fits entirely inside its window. The same configuration applies to all splits. Defaults are engineering choices fixed before the first detector run, not organiser rules or settings selected using AP/labels.

| Setting | Default | Meaning |
|---|---:|---|
| `fan_in_min_senders` | 3 | Distinct external donors to a collector |
| `fan_out_min_receivers` | 3 | Distinct external recipients of a distributor |
| `scatter_gather_min_intermediaries` | 3 | Distinct middle wallets connecting the same source and destination |
| `gather_scatter_min_senders` | 3 | Distinct donors funding a hub |
| `gather_scatter_min_receivers` | 3 | Distinct recipients paid by a hub |
| `min_group_usd` | 100 | Minimum aggregate USD; both sides for two-phase patterns |
| `min_path_leg_usd` | 10 | Minimum first delivered and second spent USD for compatible SG paths |
| `min_flow_ratio`, `max_flow_ratio` | 0.5, 1.5 | Allowed compatible forwarding and aggregate flow ratio |

Edit `aml_thresholds.json` or pass `--config path/to/config.json --run-name new_run_name`. Defaults and config/code/input/output hashes are saved in the report. No random sampling, target statistics or cross-split aggregation is performed.

Resource limits also live in the configuration: 5,000,000 candidate two-hop event pairs, 2,000,000 retained compatible paths, 5,000,000 gather-scatter candidates, 100,000,000 scatter-gather path/window checks, and 100,000,000 witness edge memberships per graph across all windows. Exceeding a limit raises an explicit error instead of producing partial detections. Only two-hop paths are enumerated; gather-scatter phase path counts are computed analytically. Resource counts and elapsed times are reported.

## Pattern and membership definitions

**ID 1: Fan-in.** At each incoming-event timestamp `T` for a collector, examine incoming user payments in `[T-W, T]`. Require the configured number of distinct senders and minimum sum of delivered USD. Every deposit in a qualifying window receives ID 1. No subsequent withdrawal is required by this shape; forwarding behaviour is retained as separate numerical context.

**ID 2: Fan-out.** At each outgoing-event timestamp `T` for a distributor, examine outgoing payments in `[T-W, T]`. Require the configured number of distinct receivers and minimum sum of spent USD. Every outgoing payment in a qualifying window receives ID 2. Funding receipts are described separately rather than automatically included in this shape.

**ID 3: Scatter-gather.** Enumerate paths `S → M → D`, with three distinct wallets, strictly increasing timestamps, delay at most seven days, and compatible middle-wallet spent/received amounts. First delivered USD and second spent USD must each meet the path minimum and their ratio must be in the configured range. For each `(S,D)`, examine all such paths ending at/before a completion timestamp `T` and starting at/after `T-W`. Require at least the configured number of distinct intermediaries. Sum source USD over unique first-leg transaction IDs and destination USD over unique second-leg IDs; require both totals above the group minimum and gathered/scattered ratio in range. All participating first/second user payments receive ID 3. Split and forwarding activity may interleave across branches, but every individual branch is strictly ordered and the whole witness span is at most W.

**ID 4: Gather-scatter.** For a hub, enumerate a collection cutoff `C` at an incoming timestamp and a completion time `T` at a later outgoing timestamp, with `T-C <= W`. Select incoming payments in `[T-W,C]` and outgoing payments in `(C,T]`. Require distinct donor/recipient thresholds, both aggregate USD amounts above the minimum, and outgoing spent USD / incoming delivered USD within the configured range. Every collection precedes every selected redistribution. All participating payments receive ID 4. Counts use each event once; path support is `incoming_event_count × outgoing_event_count`. Individual deposits need not match individual payouts: aggregation can fund differently sized outgoing payments. Donor and recipient sets may overlap, but the hub is excluded from both.

Transaction-level membership is the union of all qualifying witnesses and all windows. `aml_pattern` is a sorted unique list drawn from `[1,2,3,4]`; a row may have multiple IDs or an empty list. Parquet stores it explicitly as `list<int8>`, including datasets with only empty lists. Self-payments are retained unchanged but excluded from motif evidence and external-wallet contexts. Native conversion legs and technical liquidity providers are not expanded into graph payments or AML intermediary paths.

The two-phase flow-ratio tests use all events selected by the defined anchored window, not arbitrary cherry-picked subsets. Wider windows can therefore fail a flow-ratio check that a shorter window passes when additional activity changes aggregate balance; per-window flags need not be nested. The final ID list unions them.

## Numerical features

The output has 133 columns: original 15, `aml_pattern`, and 117 numerical features (39 per window). Counts below describe external user payments, not raw execution legs.

- Four wallet contexts each provide event count, distinct counterparties and USD sum: sender outgoing `[t-W,t]`, receiver incoming `[t-W,t]`, sender preceding incoming `[t-W,t)`, and receiver subsequent outgoing `(t,t+W]`.
- Strict prior funding delay and next forwarding delay are in seconds. Missing events use `-1`; count columns distinguish absence. Ratios are current spent USD / preceding funding USD (zero when no funding) and future outgoing USD / current delivered USD. These are activity proxies, not assertions that specific funds were forwarded.
- Forward/received compatible two-hop path counts, minimum delay and mean middle-wallet flow ratio are assigned to each leg. Parallel transaction event pairs remain distinct paths. Missing path delay is `-1`; a missing mean ratio is zero, distinguished by the count.
- Each pattern/window has a numerical `_detected` flag. Fan witnesses retain counterparty count and USD volume; SG retains path/intermediary counts, aggregate flow ratio and minimum delay; GS retains donor/recipient/path counts, aggregate flow ratio and minimum delay.

When several witnesses support a transaction, flags union all witnesses. Support metrics come from one deterministic strongest witness: fans prioritize distinct counterparties then event count; SG/GS prioritize path count. Equal-support ties retain the first witness in deterministic wallet/time/hash traversal. Metrics from different witnesses are not combined into a fictitious witness. Qualifying witness counts in the report are evaluated witness windows, not disjoint AML episodes.

All original values/types and transaction ordering are preserved exactly. USD source amounts measure actual spent asset value; destination amounts measure delivered value. Group sum calculations deduplicate transaction IDs to avoid double counting a payment participating in multiple paths. XRP fees remain separate.

`feature_schema.json` lists numerical AML columns, descriptions, recommended original numeric columns and the original `SOURCE_ASSET`/`DESTINATION_ASSET` categorical columns. Exclude `TRANSACTION_HASH`, `SENDER`, `RECEIVER` and list-valued `aml_pattern` from the future model matrix; use numerical per-window flags for motif membership. No CatBoost installation, fitting or AP evaluation is performed in this step.

## Validation and limits of interpretation

Tests cover overlapping memberships, repeated donors, self-payments, the four motif shapes, strict temporal direction/equal-time exclusions, 1h/24h boundaries, total-span limits, aggregate funding with unmatched payout sizes, deduplicated flow sums, thresholds, explicit resource failure, deterministic row shuffling, annotation neutrality, original-field preservation, finite features and list Parquet round-trips. All tests run in spawned processes using the command above.

Whole-window offline context is permitted by the supplied README. Earlier transactions can acquire a motif from later within-window payments; this is not a causal live-detection feature set. Observation boundaries truncate available history. Full train graph features must be recomputed on isolated retained fit/holdout graphs before supervised validation; the full-train artifact must not be merged into the old isolated holdout protocol.

These are broad descriptive motifs. At the default settings, seven-day fan-in/fan-out membership can saturate this dense synthetic graph. That is a reported limitation, not evidence of perfect detection: short-window flags and continuous counts/delays/ratios retain additional variation. No precision, recall, suspicious classification or improvement over the baseline is inferred from motif counts.
