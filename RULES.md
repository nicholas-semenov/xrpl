# RULES.md — Decode & Detect: XRPL AML Transaction Scoring

> **Purpose:** Operational instructions for a coding agent (Codex) implementing a reproducible machine-learning solution for the **Decode & Detect** synthetic XRP Ledger anti-money-laundering challenge.
>
> **Scope:** Data understanding, transaction reconstruction, graph analysis, feature engineering, modelling, validation, evaluation, and prediction generation **only**. This file deliberately excludes event logistics, participation arrangements, prize information, and scheduling.
>
> **Source of truth:** The supplied *Decode & Detect AML Training* deck (especially slides 7b and 8–26), the supplied *XRPL Hackathon* challenge/technical briefing (slides 8–13 and 15), and—once available—the dataset's actual `README.md`, schema, and bundled source code. **Do not invent data columns, file locations, label encoding, rates, findings, or performance numbers.**

---

## 0. How to interpret these instructions

Use the following convention throughout this document:

- **[REQUIRED — BRIEFING]**: An explicit requirement or fact in the supplied challenge materials.
- **[SOURCE FACT]**: A documented property of the synthetic dataset or XRPL-style records.
- **[RECOMMENDED — ENGINEERING]**: A proposed implementation choice intended to improve quality, speed, robustness, or reproducibility; not an organiser-mandated algorithm.
- **[VERIFY IN README/DATA]**: A detail not fully specified in the slides; check the supplied dataset documentation or inspect the actual records before implementing.

When a recommendation conflicts with verified dataset documentation, follow the verified dataset semantics. When two supplied presentations differ, flag the discrepancy and apply the more conservative data-use interpretation until clarified. Do not silently claim that recommendations are competition rules.

## 1. Exact objective and unit of prediction

**[REQUIRED — BRIEFING]** Develop a detection algorithm that uses transaction details, account relationships, timing, and currency conversions to identify transactions associated with **simulated money laundering**, while limiting false positives.

- Predict **one continuous suspicion score in the inclusive range `[0, 1]` for every test `TRANSACTION_HASH`**.
- A **higher score means greater suspicion**.
- The prediction target is **the transaction**, **not** a transfer leg, wallet, entire path, AML typology, or cluster.
- A transaction can have **multiple transfer rows**, but it receives **exactly one** prediction.
- Training labels indicate the synthetic scenario's suspicious/not-suspicious ground truth. They **do not establish real-world criminality**.
- The test labels are private and must never be inferred from prohibited sources or fabricated.

**Primary objective:** rank genuinely suspicious test transactions ahead of legitimate ones, as measured by **Average Precision**. Explicit pattern detection is a means to improve transaction-level ranking, **not a separately scored output**.

### 1.1 What counts as a successful implementation

1. It reads and validates the real supplied data without relying on fabricated schema assumptions.
2. It correctly reconstructs the economic payments and preserves transaction identity.
3. It computes useful, reproducible features without using ground-truth labels as predictors.
4. It trains, validates, and selects models based primarily on **validation Average Precision**.
5. It produces a fully validated CSV covering the exact test transaction set.
6. It can reproduce features, model training, validation scores, and test scores from documented code/configuration.

## 2. Available datasets and their roles

**[SOURCE FACT]** The described synthetic dataset follows the **AWS/SonarX XRP Ledger schema**. The provided materials state:

| Input | Documented role | Critical handling |
|---|---|---|
| `transactions.parquet` | One record per transaction; transaction-level fields, sender, fees, payment information including JSON text | Preserve unique `TRANSACTION_HASH`; parse documented JSON fields |
| `transfers.parquet` | Economic transfer legs associated with each transaction; typically **1–3 rows per transaction** | Join using `TRANSACTION_HASH`; do **not** count every leg as a separate end-user payment |
| `blocks.parquet` | Ledger index, block/ledger hash, close time | Use verified transaction-to-ledger join keys and consistent timestamps |
| `market_rates.csv` | Hourly reference prices in USD for assets | Value transfers using the reference rate for the hour containing the payment |
| `labels.csv` | Ground-truth suspicious labels for the **training** split only | Join only by the verified transaction identifier; never expose as model features |
| `README.md` | Exact data schema, meanings, assumptions, edge cases | Read before making definitive parsing decisions |
| `payments.py` | Bundled helper referenced in training for **one logical edge per payment** | Read and run if supplied; inspect its assumptions and outputs |
| `baseline.py` | Bundled working baseline referenced in training | Run early if supplied; retain its output and validation results as comparison |

**[SOURCE FACT]** Published transaction counts:

- **40,131 labelled training transactions**.
- **40,101 unlabelled test transactions**.
- Approximately **7 days of activity per split**.

**[VERIFY IN README/DATA]** Determine the physical layout of train/test files, actual column names beyond those explicitly mentioned, dtypes, precise label column and encoding, rate-key schema, timestamp units/timezone, transaction types, and all possible JSON representations. The slides do not provide a complete machine-readable schema. The real README and input inspection supersede guesses.

### 2.1 Initial data audit (mandatory engineering gate)

Before modelling, emit a concise audit report covering:

- Files actually present, row counts, field names, dtypes, missingness, and duplicate keys.
- Count of unique `TRANSACTION_HASH` values in train and test; confirm the expected values or explain any mismatch.
- Number of transfer rows per transaction; inspect cases with 1, 2, and 3 legs.
- Types and examples of `EXTRA_TRANSACTION_FIELDS` and `DELIVERED_AMOUNT` when present.
- Time range, ledger coverage, missing rate joins, asset distribution, and rare/unusual values.
- Training label distribution, prevalence, and any evidence of distinct scenario types **only if disclosed in the data**.
- Whether train/test are independent synthetic histories, share wallet identifiers, or have overlapping time windows; do not assume they can be combined into a single economic graph.

Keep exploration summaries; do not invent statistics before reading data.

## 3. XRPL-style domain invariants and pitfalls

The training presentation specifically warns about the following. They must be reflected in parser logic and automated tests.

### 3.1 Transaction versus transfer

**[REQUIRED — BRIEFING]** Join relevant records on `TRANSACTION_HASH`. A currency conversion can be **one transaction involving two or three transfer legs** through liquidity providers. Model a **single original transaction** with its actual payer/recipient and conversion information, not 2–3 independently labelled payments.

**[RECOMMENDED — ENGINEERING]** Keep both representations:

1. A **canonical economic-payment table**: one payment/event record per actual transaction, including payer, intended receiver, timestamp, input asset/value, output asset/value, USD value, conversion characteristics, and `TRANSACTION_HASH`.
2. A **raw leg table**: all transfer legs, preserved for precise conversion tracing and network/liquidity features.

Do not naively sum all leg amounts or count liquidity-provider hops as money-laundering wallet hops. If `payments.py` exists, inspect and prefer its well-defined reconstruction before building a replacement.

### 3.2 Native XRP units

**[SOURCE FACT]** `1 XRP = 1,000,000 drops`. For **XRP rows**, the training deck says `SOURCE_VALUE` is in **drops**. Convert those values to XRP before comparing with token amounts or USD prices. **Do not divide unrelated issued-token values by 1,000,000.**

### 3.3 Issued-asset identity

**[SOURCE FACT]** An issued token is identified by **issuer/address plus currency code**; in the supplied transfer representation use **`TOKEN_ADDRESS` + `SYMBOL`** where applicable. The same `USD` symbol from two issuers represents two **different assets**. Keep a deliberate representation for native XRP, which need not have an issued-token address.

### 3.4 Input versus output amount

**[SOURCE FACT]** `SendMax` is a **ceiling**, not the amount actually paid. The first transfer leg captures the actual asset/value spent; `DELIVERED_AMOUNT` describes what reached the receiver. Handle conversions as a single transaction with distinct **spent** and **delivered** assets/amounts.

**[VERIFY IN README/DATA]** Confirm which transaction types expose these fields, exact JSON shape, leg ordering, and how to interpret missing amounts or partial-payment details. Never use `SendMax` as realised cost merely because it is convenient.

### 3.5 Fees

**[SOURCE FACT]** The training deck describes network fees of roughly **10–15 drops of XRP**, burned even for token-payment transactions in this synthetic setup. Keep fees distinct from delivered value. Do not treat burnt fees as transfers to a receiving wallet.

### 3.6 Reference USD value

**[SOURCE FACT]** Compare heterogeneous assets in **USD**, using `market_rates.csv` and the reference **hour containing the payment**. Resolve the correct asset identity before rate joining.

**[RECOMMENDED — ENGINEERING]** Preserve original asset and amount alongside normalized XRP/USD. Report all missing/unmatched rates; never silently fill with a guessed rate of 1. Prevent forward-looking joins to unrelated hours. Decide and document how to handle missing prices and zero/invalid values.

### 3.7 JSON, time, identities, observation window

- **[SOURCE FACT]** Some fields are JSON text; explicitly parse `EXTRA_TRANSACTION_FIELDS` and `DELIVERED_AMOUNT` when present, without corrupting nulls, arrays, or nested structures.
- **[SOURCE FACT]** Ledger data reveals addresses, transfers, timing and conversions, but **not** verified identity, transaction purpose, off-ledger cash/bank movements, or activity beyond the seven-day window.
- **[RECOMMENDED — ENGINEERING]** Use timezone-aware timestamps, deterministic ordering for ties, and explicit window boundaries. Avoid any assertion about wallet owners or actual criminal intent.

## 4. Canonical preprocessing and reconstruction pipeline

**[RECOMMENDED — ENGINEERING]** Implement the following pipeline as deterministic, independently testable stages:

1. **Discover inputs.** Locate files; read README and bundled scripts. Fail clearly if essential inputs are missing.
2. **Load safely.** Read Parquet/CSV with stable types; preserve transaction hashes as strings; do not round high-precision values prematurely.
3. **Parse and validate.** Decode JSON and timestamps; normalize nulls; validate transaction/transfer relations and key integrity.
4. **Reconstruct logical payments.** Build one transaction-level record per payment, using `payments.py` when available; distinguish direct payments from conversions and extract actual delivered/spent values.
5. **Normalize amounts.** Convert XRP drops correctly, retain token issuer+symbol identity, and value amounts in USD with the appropriate hourly rate.
6. **Build time-aware histories.** Sort each split's payments by event time plus deterministic tie-breaker; preserve original input transaction ordering for output.
7. **Prepare labels.** Attach training labels by validated transaction IDs; keep hidden test targets absent.
8. **Validate invariants.** Ensure no accidental row multiplication or loss of transaction coverage at any join.
9. **Cache intermediate results.** Store versioned deterministic processed tables/features for reproducibility and fast iteration.

Do not assume that all transactions are ordinary transfers. Inspect non-payment types and decide how to create features and scores for **every** supplied test transaction; do not silently drop them.

## 5. Build a temporal directed money-flow graph

**[RECOMMENDED — ENGINEERING]** Use the economic-payment representation as the main graph:

- **Node:** XRPL wallet/account address (opaque ID, not a real-world identity).
- **Directed edge/event:** payer `→` payee for a canonical payment, retaining `TRANSACTION_HASH`.
- **Edge attributes:** timestamp, paid amount/asset, delivered amount/asset, normalized USD value, conversion flag/path attributes, optional fee and ledger metadata.
- **Graph type:** directed **multi**graph or equivalent event table; repeated payments between the same wallets must remain distinguishable.

For event-time features, a transaction should retain both sender-side and receiver-side context. Build per-wallet incoming/outgoing event histories, and optionally pair-level/asset-level histories. Use appropriate time windows (e.g., 5 minutes, 1 hour, 6 hours, 24 hours, all observed days) **as tunable engineering choices**, not claimed dataset rules.

### 5.1 Two acceptable information-availability protocols

The slides describe a seven-day history and **do not explicitly specify** whether scoring is performed after observing the entire window or in real time. Implement and document one or both protocols consistently:

- **Causal/as-of-event:** compute features using information available **at or before** each transaction. Never include later events. Preferred robust baseline.
- **Full-window/offline analysis:** features may use future-within-window, post-transaction forwards or whole-week topology **only if verified as allowed for the supplied task**. If used, evaluate using the same availability assumptions and report the distinction.

**Absolutely forbidden:** ground-truth labels, test-label guesses, or label-derived aggregates from held-out evaluation records entering prediction features. **Do not call legitimate unlabeled full-window graph use “label leakage”; instead, clearly identify the transductive assumption and test its stability.**

## 6. Feature engineering: practical priority order

**Core principle:** a graph shape alone is **not proof** of money laundering. Exchange hot wallets, payroll, merchant collections, payment processors, market making, arbitrage, internal treasury transfers, refunds, bots, and testing activity can create similar shapes. Features should describe behaviour; the supervised model learns how features relate to **training labels**.

### 6.1 Group A — basic transaction and asset features (first implementation)

Implement where supported by real columns:

- `amount_usd`, `log1p_amount_usd`, original amount and units.
- Paid-asset ID and delivered-asset ID; native XRP versus issued token.
- `is_asset_conversion`, input/output asset difference, conversion count within a transaction, and realized exchange rate where derivable.
- Transaction timestamp (e.g., hour of day, day within observation window) and time since preceding account activity.
- Fee in XRP and normalized fee/value ratio where meaningful.
- Missing-value/rate/parse-success indicators; transaction type where available.

Do **not** use arbitrary raw transaction hashes as predictive features; they are identifiers, not meaningful explanatory measurements.

### 6.2 Group B — wallet and counterparty behaviour (high priority)

For both sender and receiver, calculate within appropriate observation windows:

- Inbound/outbound transaction counts and transaction rates.
- Number of **distinct** senders and **distinct** recipients; directional degree.
- Total/mean/median/max inbound and outbound USD values; dispersion of amounts.
- Time since first/most recent inbound/outbound transaction, burstiness, inter-arrival statistics.
- Recent inbound versus outbound value and volume ratios, computed with safe denominators and explicit missingness.
- Wallet age **within the observed window** (not a claim about the wallet's true age).
- Number/share of one-time counterparties, concentration of flows among counterparties, repeated-pair activity.
- Asset diversity, conversion share, number of asset changes, changes in token/issuer identity.
- Difference or overlap between recent inbound and outbound counterparty sets.

### 6.3 Group C — temporal flow and intermediary behaviour (high priority)

Where consistent with the chosen time-availability protocol:

- Delay from a wallet's receipt of funds to its subsequent outward payment.
- Fraction of recent incoming USD value subsequently forwarded within a specified interval.
- Payout value compared with recent deposits, allowing explicitly modelled fees and conversion-rate differences.
- Number of **short-time, temporally ordered** paths through low-activity intermediaries.
- Similarity of timings and values among coordinated outgoing or incoming transactions.
- Transactions following wallet funding after an unusually short interval.

**Caution:** Fast pass-through is also seen in legitimate automated services; tiny circular activity can be bots/tests. Combine timing with economic scale and topology rather than assigning a fixed positive label.

### 6.4 Group D — graph topology and neighbourhood features (add incrementally)

- Weighted/unweighted in-degree and out-degree, reciprocal counterparties, local clustering proxies.
- Degree statistics of immediate neighbours, two-hop neighbourhood size, shared counterparties.
- Counts of temporally valid 2-hop and limited 3/4-hop routes.
- Connected-component/community size, edge density, number of internal/external contacts.
- Short-cycle participation, cycle length, elapsed time and value retained.
- Local source/sink/hub indicators and relative inflow/outflow activity.
- Approximate graph centralities **only when computationally practical and informative**.

Avoid uncontrolled enumeration of all paths/cycles; on dense graphs these searches can explode combinatorially. Cap hop depth, time horizon, degree and path counts; use sparse operations/caching and test runtime.

## 7. The eight AML pattern families to investigate

**[SOURCE FACT]** The training deck gives **eight** synthetic laundering-pattern families, with legitimate look-alikes. This is a feature-engineering guide—not a requirement to label a transaction with an exact pattern class and **not** an instruction to mark all pattern members as positive.

### 7.1 Fan-in — many sources, one collector

**Shape:** Many accounts fund a collector; the collector may make one/few large exit payments.

**Useful features:** unique inbound counterparties in short windows; novelty/low prior activity of sources; time from accumulation to exit; exit USD value relative to recent incoming USD sum; collector balance/flow profile.

**Benign confounders:** merchant payments, fundraising, exchange deposit addresses.

### 7.2 Fan-out — one source, many recipients

**Shape:** A funded source splits value across numerous receivers; receivers may forward rapidly.

**Useful features:** unique outbound counterparties; payout amount similarity/coefficient of variation; fraction of recipients with rapid subsequent forwarding; short time since source funding.

**Benign confounders:** payroll, refunds, giveaways, exchange withdrawals.

### 7.3 Scatter-gather — split, intermediate, reconverge

**Shape:** Source `S` pays several middle wallets `M_i` that later pay common destination `D`.

**Useful features:** temporally valid two-hop route count for `(S,D)`; distinct middlemen; closeness of source sum and destination sum after fee/rate adjustments; middlemen's low other activity; similar holding times.

**Benign confounders:** internal business transfers, exchange rebalancing.

### 7.4 Gather-scatter — many sources, hub, many destinations

**Shape:** A hub gathers from many sources and redistributes to other wallets.

**Useful features:** simultaneous high inbound/outbound unique counterparty counts; low retained value relative to throughput; short in→out interval; limited overlap of inbound versus outbound counterparties; mirrored hourly flows.

**Benign confounders:** exchanges, payment processors, payroll services.

### 7.5 Cycle — value returns to an earlier wallet

**Shape:** `A → B → C → ... → A`, possibly switching assets.

**Useful features:** temporally ordered return paths, hop count, cycle duration, returned-versus-sent value ratio in USD, changes in assets and issuers during the route.

**Benign confounders:** arbitrage, market making, refunds, self-controlled wallets.

### 7.6 Layered stack — several intermediary layers

**Shape:** Value moves from source to destination through successive layers of wallets.

**Useful features:** bounded path depth, one-use or low-activity middle wallets, proportion of value preserved across steps, regularity of inter-hop delays, minimal side activity.

**Benign confounders:** payment processing chains, business-to-business transfers.

### 7.7 Bipartite — two densely connected groups

**Shape:** Members of group A repeatedly fund members of group B, with many-to-many relationships.

**Useful features:** density of edges between two inferred sets, few outside contacts, common activity windows, similar pair values, unusual cross-group concentration.

**Benign confounders:** marketplaces, supplier payments.

### 7.8 Irregular network — branching, merging, returning flows

**Shape:** Non-template networks with several partial routes, forks, merges and occasional returns.

**Useful features:** connected-subgraph size/density, bounded distinct paths between relevant entry/exit points, internal throughput vs outward movement, concentration of events in time, composite graph-motif statistics.

**Benign confounders:** ordinary peer-to-peer and community transactions.

### 7.9 Implementation guidance for typologies

1. First implement inexpensive, continuous **behavioural features**. They implicitly capture parts of fan-in/fan-out/gather-scatter.
2. Then add bounded, **time-respecting two-hop scatter-gather** and short-cycle features.
3. Add deeper layering, bipartite and irregular-network features only after validating incremental AP gain versus runtime.
4. Give every transaction features representing **its role** (source, middleman, collector, exit) if possible; avoid indiscriminately assigning the same suspicion level to every edge of a matched subgraph.
5. Store detected motifs only as **features or investigative explanations**; the supervised ground truth remains the supplied transaction label.

## 8. Labels, sampling and supervised modelling

**[RECOMMENDED — ENGINEERING]** Use supervised binary classification **as the first strong approach**, because the training split has transaction-level ground-truth labels. CatBoost and LightGBM are good tabular baselines; a GNN or ensemble may be tried later. Reinforcement learning is **not necessary** for the stated static ranking task.

### 8.1 Label handling

- Derive the exact label field and encoding from `labels.csv`/README.
- Verify that every labelled training `TRANSACTION_HASH` maps to exactly the intended transaction and that no duplicate/conflicting labels exist.
- Never manufacture positive labels from heuristic motif matches, balance changes, or score thresholds.
- Never include labels, row ordering correlated with labels, train/test origin flags, or post-hoc label statistics as predictors.
- If doing any target encoding or label-derived group aggregation, perform it **out of fold** with proper separation; simpler is to omit it initially.

### 8.2 Recommended model sequence

**Model 0 — provided baseline:** run `baseline.py` if available and verify its score-generation process; establish a known-good comparison.

**Model 1 — tabular baseline:** CatBoost or LightGBM on transaction, asset and simple wallet-history features.

**Model 2 — behavioural model:** add temporal pass-through, distinct-counterparty, flow and local graph statistics.

**Model 3 — bounded motif model:** add selected AML pattern features with demonstrated value.

**Model 4 — optional:** compare alternative boosting model, calibrated or uncalibrated blending/rank averaging, or graph neural networks if time and evidence justify them.

Track each model/configuration/feature set and its **held-out AP**. Do not assume a larger model or all eight motif detectors will improve performance.

### 8.3 Suggested training practices

- Fix random seeds; save model configuration, package versions and feature list.
- Use stratified sampling when appropriate for a simple first validation, but do not let it be the **only** validation if graph/time correlations are present.
- Consider class weights only after measuring baseline and changes in held-out AP; weighted training can alter ranking.
- Choose number of trees/learning rate/depth through validation, with early stopping where supported.
- Handle missingness natively or with consistent train/validation/test imputation; prevent fitting imputers on withheld labels.
- Examine feature importance and high-ranked false positives; target the failure modes revealed by real validation errors.
- Never tune on private labels or claim a particular score before measuring it.

## 9. Validation design and leakage prevention

**[REQUIRED — BRIEFING]** Hold out part of the labelled training examples to evaluate predictions on transactions not fitted by the model. Evaluate using **Average Precision**.

**[RECOMMENDED — ENGINEERING]** Use a consistent feature-availability protocol and at least one validation scheme that challenges easy memorization:

1. **Initial sanity check:** a stratified transaction-level holdout can verify that end-to-end modelling works; label it a potentially optimistic diagnostic when nearby graph events cross the split.
2. **Primary robust check:** prefer a time-based holdout where feasible. Compute causal features as of each transaction, if claiming live detection.
3. **Supplementary stress test:** when possible, create group/component-aware or scenario-aware holdouts to measure behaviour on unseen wallet communities; document any practical limits in forming these splits.
4. **Full-window approach:** if allowed, distinguish unlabeled graph information available at scoring time from training targets. Do not leak held-out labels via joins, target encodings or training statistics.
5. Ensure all feature transformations, selection, thresholds, hyperparameter fitting, target statistics and preprocessing are applied consistently and without forbidden supervision leakage.
6. Estimate variability across folds/time slices and inspect the hardest missed positives and highest-ranked benign cases.
7. Distinct train and test synthetic scenarios may differ; avoid validation choices that merely exploit repeated wallet IDs or other unstable shortcuts.

### 9.1 Concrete leakage checklist

- [ ] Are validation labels excluded from *all* learned training-side target statistics?
- [ ] Does an `as_of` feature accidentally include payments after the scored event?
- [ ] If using full-window features, is this permitted and evaluated consistently?
- [ ] Are wallet/graph aggregates from distinct synthetic worlds kept apart unless explicitly justified?
- [ ] Are normalizations, imputations, encodings and feature selection fitted according to the chosen evaluation protocol?
- [ ] Can any raw identifier, join artifact, row index or filename leak train/test membership or scenario labels?
- [ ] Are synthetic motif IDs or generation hints used only if disclosed/permitted, and not as a substitute for behavioural detection?

## 10. Scoring: what actually matters

**[REQUIRED — BRIEFING]** Official ranking metric:

```text
Challenge score = 100 × Average Precision (AP)
```

Average Precision rewards putting **suspicious transactions ahead of legitimate transactions across the entire test file**. For strictly ranked predictions with `P` actual positives, an intuitive expression is:

```text
AP = (sum of Precision@rank over ranks occupied by positives) / P
```

In implementation, use `sklearn.metrics.average_precision_score(y_true, score)` or a verified equivalent, respecting its treatment of tied scores.

**Operational implications:**

- Optimize and select primarily on **AP**, **not** accuracy, fixed-threshold F1, log loss or ROC-AUC.
- Scores are **ranking values** and need not be perfectly calibrated probabilities.
- Avoid degenerate predictions (all 0/1 or many exact ties); produce informative, continuous scores.
- All scores must still be finite and within `[0, 1]`.
- Do not threshold test predictions into binary flags for final output.
- **Secondary diagnostics:** ROC-AUC and precision/recall/F1 for the **top 1% (402 transactions)**. These are useful analyses but **not additional score components**.
- Analyze performance on positives and benign look-alike patterns. Presentation notes that suspicious cases are described as **64% easy, 18% medium, 18% hard**; those percentages concern **suspicious-case difficulty**, not class prevalence. Difficulty labels might not be present in `labels.csv`; do not assume they are available.

## 11. Prediction generation and exact CSV contract

**[REQUIRED — BRIEFING]** Generate one row **per test transaction** with exactly these columns, spelled and cased as shown:

```csv
TRANSACTION_HASH,score
<actual_test_transaction_hash>,0.82
<another_actual_test_transaction_hash>,0.07
```

The placeholder strings above are illustrative; actual hashes must come directly from the supplied test data.

**CSV invariants:**

1. Exactly **40,101 data rows** if the supplied test count matches the documented challenge.
2. Every test `TRANSACTION_HASH` appears **once and only once**.
3. No missing, duplicated, unknown, or additional transaction IDs.
4. `score` is numeric, finite, not null, and `0 <= score <= 1`.
5. No unintended index column, header variation, auxiliary columns or extra rows.
6. Prediction values must follow the exact correct **hash-to-feature-to-score alignment**; never rely on coincidental ordering after joins/sorts.
7. Predicted scores attach to transactions, not individual transfer legs.
8. Prefer using the supplied prediction template, when available, to preserve exact schema/order.

### 11.1 Required machine checks before writing or using the CSV

Use a fail-fast validation equivalent to:

```python
assert list(pred.columns) == ["TRANSACTION_HASH", "score"]
assert len(pred) == len(test_transactions)
assert pred["TRANSACTION_HASH"].notna().all()
assert pred["TRANSACTION_HASH"].is_unique
assert set(pred["TRANSACTION_HASH"]) == set(test_transactions["TRANSACTION_HASH"])
assert pd.api.types.is_numeric_dtype(pred["score"])
assert np.isfinite(pred["score"].to_numpy()).all()
assert pred["score"].between(0, 1).all()
```

Read the produced CSV back from disk and re-run these assertions. Require matching unique counts even when earlier steps appeared successful.

## 12. Engineering workflow for Codex

**Recommended order: first produce a valid working predictor; then improve AP.** The following milestones have explicit completion criteria. Avoid spending the entire project building a perfect eight-pattern detector before training anything.

### Phase A — repository/data reconnaissance

- Read `README.md` and all supplied helper scripts before changing them.
- Find train/test data, schemas, labels, pricing references and any prediction template.
- Record verified column meanings and uncertain assumptions.
- Run dataset audits and save the results.

**Done when:** train/test hashes, labels, time, asset/amount semantics and basic dataset integrity are understood and checked.

### Phase B — canonical baseline end to end

- Run provided `payments.py`/`baseline.py` if they exist.
- Construct a minimal transaction-level feature table and train a basic supervised model if required.
- Generate a valid CSV with exact transaction coverage and perform strict checks.
- Measure a held-out AP using training labels only.

**Done when:** an entirely reproducible pipeline can produce an internally validated prediction file, before any complicated graph search.

### Phase C — wallet and temporal features

- Build time-window counts, unique counterparties, amount aggregates, ratios and asset-conversion indicators.
- Add fast pass-through and hub features if permitted by feature-availability assumptions.
- Cache per-wallet event histories and test transaction/feature alignment.
- Run ablation: baseline versus each newly added group.

**Done when:** the feature contribution is measurable in validation AP; keep or remove features based on evidence.

### Phase D — targeted graph motifs

- Implement time-respecting 2-hop paths, short cycles, fan-in/fan-out and gather-scatter motif features first.
- Only then consider deeper layered routes, bipartite density and irregular subgraphs.
- Add runtime guardrails and unit-test motifs on tiny manually constructed **synthetic toy examples** (not fabricated real dataset findings).

**Done when:** motif features are correct, bounded in runtime, and improve AP or provide a documented useful analysis.

### Phase E — modelling and robustness

- Compare CatBoost and LightGBM on identical, fold-consistent feature sets.
- Tune cautiously using held-out AP and avoid overfitting a single validation split.
- Diagnose benign hubs, conversions, low-value bot-like cycles and unseen test-like behaviours.
- Try an ensemble only if independently verified to improve held-out ranking.

**Done when:** a chosen model/configuration is supported by reproducible validation evidence.

### Phase F — deterministic final inference

- Recompute the exact selected features on the test inputs using the documented, permissible information protocol.
- Fit final model on the permitted labelled training data with the finalized hyperparameters.
- Produce and re-read the CSV, assert exact transaction coverage, inspect score spread/ties.
- Preserve model artifacts, configuration, feature definitions, and a minimal explanation of method and limitations.

**Done when:** a single documented command can regenerate equivalent test scores from the supplied inputs.

## 13. Suggested code structure (adapt to the actual repository)

**[RECOMMENDED — ENGINEERING]** Use clean modules instead of a single opaque notebook where possible:

```text
project/
  RULES.md
  README.md                    # implementation/run instructions
  config/                      # seeds, feature windows, paths, models
  src/
    data_io.py                 # schema discovery, load, validation
    xrpl_normalize.py          # amount/asset/time/JSON normalization
    payment_reconstruction.py  # canonical economic payments
    graph_features.py          # account histories and motifs
    features.py                # transaction-level feature matrix
    validation.py              # leakage-aware splits and metrics
    train.py                   # train / select / save
    predict.py                 # produce test scores
    validate_submission.py     # strict CSV contract checks
  tests/
    test_xrpl_units.py
    test_payment_conversion.py
    test_graph_motifs.py
    test_features.py
    test_submission.py
  outputs/                      # generated audit, models, metrics, predictions
```

This is **an optional target structure**, not a claim that these files already exist. Reuse supplied scripts and existing conventions instead of duplicating tested functionality. If the existing project is small, a leaner structure is preferable.

### 13.1 Code-quality rules

- Use Python type hints and docstrings for non-trivial parsing/graph functions.
- Keep I/O, parsing, feature computation, fitting and inference separate and testable.
- Preserve transaction IDs throughout transformations, without relying on row order.
- Log record counts and null/duplicate joins at every major stage; raise on critical integrity failures.
- Make the pipeline deterministic with explicit random seeds and stable sort keys.
- Use configuration for paths, features/windows, model hyperparameters and evaluation splits.
- Handle floating-point precision, zero division, missing rates, empty wallets and isolated graph nodes explicitly.
- Prefer simple pandas/Polars/SQL aggregations for local features before expensive graph algorithms.
- Avoid use of outside transaction datasets or scraped addresses unless explicitly authorised.
- Store no credentials or secrets in code/artifacts.
- Do not claim measured AP, precision, recall or leaderboard scores without the actual metric output.

## 14. Unit and integration tests worth writing first

Implement focused tests for:

1. **XRP conversion:** exactly 1,000,000 drops becomes 1 XRP; non-XRP amounts remain in their native units.
2. **Distinct issuers:** same symbol from two issuers stays two separate assets.
3. **Conversions:** two/three transfer legs reconstruct into one logical scored transaction; spent and delivered values are distinguishable.
4. **SendMax:** a ceiling never overrides actual paid amount.
5. **Fees:** burned XRP fee is excluded from recipient value and does not create a transfer edge.
6. **Rate joining:** correct asset and containing hour; controlled behaviour for missing rates.
7. **Time order:** causally invalid path `B→C` occurring before `A→B` is not counted as a forwarded `A→B→C` flow.
8. **Graph multiplicity:** repeated pair payments remain distinct events.
9. **Motifs:** fan-in, fan-out, scatter-gather, gather-scatter and cycle toy graphs yield expected counts; benign look-alikes are not automatically assigned positive labels.
10. **Leakage:** no label column or validation-derived target statistic appears in the feature matrix; feature availability matches declared protocol.
11. **Join integrity:** each expected transaction is represented once after every transaction-level merge.
12. **Output schema:** row count, exact hash-set match, finite scores in `[0,1]`, uniqueness, stable output after serialization.

## 15. Experiments and interpretation

Maintain a lightweight experiment log with at least:

| Field | Record |
|---|---|
| Model/run ID | Code version, seed, model name and parameter configuration |
| Feature set | Groups enabled, temporal lookback windows, motif depth |
| Feature availability | Causal vs permitted full-window, whether separate worlds are mixed |
| Validation protocol | Split method, time boundaries/groups and sample counts |
| Main result | Average Precision on truly held-out labelled transactions |
| Diagnostics | ROC-AUC, top-402 precision/recall/F1, score distribution, major false positives |
| Cost | Feature runtime, fit runtime, resource use when measurable |
| Limitations | Missing rates, unknown transaction purposes, truncated histories, unstable motifs |

Compare models using the **same** validation data wherever possible. Report meaningful uncertainty and avoid presenting synthetic-dataset AP as proof of effectiveness on real-world financial crime.

## 16. Data-use and reproducibility guardrails

**[SOURCE FACT / CONSERVATIVE INTERPRETATION]** The training deck states **no external transaction or reference data without approval**, and allows public documentation/papers. The later briefing allows reference material but requires disclosure of external sources. **Safest implementation rule:** use only the supplied transaction, ledger, rate and training-label datasets for model input unless additional data is expressly permitted; document any external informational materials.

**[SOURCE FACT]** Coding assistants, LLMs, existing libraries and pretrained models are allowed. If an AI model/LLM materially participates in an analytical method, preserve its provider/model, relevant prompts/settings and reproducibility limitations in the technical records. Keep an executable path that does not depend on hidden, undocumented manual actions.

**[RECOMMENDED — ENGINEERING]** Deliver reproducibility artifacts for the solution itself:

- Explicit package versions (requirements/lockfile or equivalent).
- Exact command(s) that regenerate processed features, train/validate and predict.
- Seed and configuration file(s).
- Model artifacts or a documented deterministic regeneration path.
- Validation metrics tied to a specific experiment and feature set.
- Technical summary of methodology, features, model choice, evaluation, interesting findings and limitations.

## 17. Decisions that must be resolved from the actual files

**Do not proceed by fabricating answers** to these unresolved details; inspect the sources and report ambiguity:

- Exact physical train/test directories, filenames and the supplied prediction template.
- Label column name, label encoding and whether labels attach to every training transaction.
- Exact transaction types and necessary fields for canonical payer/payee and conversion reconstruction.
- `EXTRA_TRANSACTION_FIELDS` and `DELIVERED_AMOUNT` data types and shapes.
- Asset/rate join keys, timestamp formats, missing-rate policy and issuer semantics.
- How the bundled `payments.py` handles conversions, special payment types and failed/non-payment transactions.
- What information is legitimately available when scoring each transaction (causal versus end-of-week context).
- Whether training and test represent separate worlds and whether wallet IDs overlap meaningfully.
- Whether any scenario, typology or difficulty metadata is included in the actual training package.

Ask for missing essential files only when necessary; otherwise build a conservative, testable baseline and list assumptions explicitly.

## 18. Non-negotiable failure conditions

**Never**:

- Submit or model **transfer legs** as if they were independent labelled transactions.
- Use `SendMax` as the actual spent amount without verified justification.
- Treat USD/GBP/EUR currency symbols alone as unique asset identities.
- Mistake XRP drops for whole XRP.
- Add value across multiple conversion legs as though it were new money.
- Treat every member of a detected graph motif as automatically suspicious.
- Use private/held-out test ground truth, fabricated labels, or prohibited external transaction data.
- Optimize solely for accuracy or a 0.5 threshold while ignoring Average Precision.
- Produce duplicate, missing, extra or non-finite test predictions.
- Present anecdotal pattern matching as proof of financial crime.
- Claim a model, metric, script or column exists without verifying it in the actual supplied files.

---

## 19. Codex execution directive

**Start by inspecting the actual repository, README, source files, and data schema.** Summarize verified inputs, detect ambiguities, then build the smallest correct end-to-end transaction-level prediction pipeline. **Get a reproducible baseline and validation AP before adding advanced AML pattern detectors.** Use measured ablations to choose features; prefer a strong, well-validated CatBoost/LightGBM model with meaningful wallet/flow/graph features over an untested complex architecture. Ensure every implemented stage respects XRPL units, asset identities, conversion legs, label separation and exact hash alignment. Finish with a machine-checked prediction CSV and deterministic instructions to regenerate it.

**Final principle:** **Patterns inform features; supervised evidence informs scores; Average Precision determines ranking quality.**
