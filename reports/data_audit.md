# Supplied data audit

Verified on 2026-10-24 using the supplied files, README, payment helper and starter notebook. No model was trained and no validation AP was measured.

## Reproduce

Run `python3 scripts/audit_data.py` from the repository root. The script validates source files and writes `reports/data_audit.json`, containing exact schemas, null counts, distinct counts, label breakdowns, numeric summaries, versions and cross-split overlaps. It does not modify datasets or train models.

Verified environment: Python 3.10.15, pandas 2.3.0, NumPy 2.2.6, PyArrow 23.0.0. Assertions must remain enabled (do not use Python's `-O` flag).

## Available splits

| Split | Directory | Transactions | Transfer legs | Blocks | Labels | Transaction dates, UTC |
|---|---|---:|---:|---:|---|---|
| Train | `data/traning_data/train` | 40,131 | 60,557 | 151,200 | Yes | Sep 1–7, 2026 |
| Practice validation | `data/traning_data/validation` | 33,862 | 55,897 | 151,200 | No | Sep 10–16, 2026 |
| Test | `data/test_data` | 40,101 | 65,272 | 151,200 | No | Sep 20–26, 2026 |

The on-disk spelling is `traning_data`. Each split contains 700 distinct payment/transfer wallets, with zero wallet or transaction-hash overlap between any pair of splits. These are separate synthetic histories; wallet IDs cannot support cross-split memorization. Each block window covers seven days; the final boundary block closes at midnight on the following date.

## Tables and useful information

- `transactions.parquet`: 26 columns, one row per successful `Payment`. Includes sender (`ACCOUNT`), timestamp, ledger identity, transaction order, sequence, fees, delivered amount and payment JSON. Parse `Destination`, `Amount`, `DeliverMax`, optional `SendMax` and `Paths` from `EXTRA_TRANSACTION_FIELDS`. Hashes are join keys, not predictive measurements.
- `transfers.parquet`: 16 columns describing ordered executed legs. `(TRANSACTION_HASH, TRANSFER_INDEX)` is unique; indices start at zero and are contiguous. First-leg sender equals transaction sender; last-leg recipient and amount match the intended destination and delivered amount. Use the first leg for actual spending and the last leg for delivery. Retain issuer identity and do not sum conversion legs as separate payments.
- `blocks.parquet`: 17 columns providing ledger metadata and timing. Join on `(LEDGER_INDEX, LEDGER_HASH)`; a block's `TRANSACTION_HASH` is not the payment join key. Blocks include empty ledgers, so their row count exceeds the payment count.
- `market_rates.csv`: 850 rows per split, five assets over 170 reference hours. Assets are XRP, USD from each of two issuers, GBP from one issuer and EUR from the other. Issuer addresses differ between splits. Divide `PRICE_MICRO_USD` by one million and select the containing hour.
- `labels.csv`: 40,131 rows, covering the exact training transaction set. Only `is_suspicious` is the supervised target. `family`, `difficulty`, `scenario_id`, and `cohort_id` are private annotation metadata; exclude them from predictors. They can support training-only diagnostics and explicitly documented evaluation grouping.

Ledger indices and timestamps use Arrow decimal types; UTC datetime columns use millisecond precision. Transaction amount fields are JSON text: native XRP decodes to a string of integer drops, while IOUs decode to objects with currency, issuer and value. Transfer `SOURCE_VALUE` is drops for XRP and token units for IOUs; `VALUE` already holds whole XRP/token units. Fees are 10, 12 or 15 drops and are separate from the delivered payment.

Seven transaction columns are entirely null in every split: `ACCOUNT_TRANSACTION_ID`, `MEMOS`, `SIGNERS`, `SOURCE_TAG`, `SIGNING_PUB_KEY`, `TICKET_SEQUENCE`, `TXN_SIGNATURE`. Transaction type, flags, success and result are constant. These fields currently provide no variation for learning. Required payment fields, transfer columns and block columns have no missing values.

## Training labels

| Class | Transactions | Share |
|---|---:|---:|
| Ordinary | 38,881 | 96.885% |
| Suspicious | 1,250 | 3.115% |

Suspicious difficulty counts: 800 easy, 225 medium, 225 hard. All ordinary records have `difficulty=normal`; this makes that annotation direct target leakage if used as a feature.

The actual label file contains 13 `family` values, rather than a ready-made eight-class classification task:

| Family annotation | Ordinary | Suspicious |
|---|---:|---:|
| background | 18,000 | 0 |
| aggregate_relay | 10,098 | 102 |
| distributed_relay | 9,702 | 98 |
| multi_stage | 165 | 173 |
| fan_out_in | 152 | 178 |
| bipartite | 152 | 134 |
| random | 178 | 80 |
| stack | 104 | 116 |
| cycle | 113 | 78 |
| fan_in | 76 | 101 |
| fan_out | 75 | 92 |
| chain | 66 | 73 |
| ambiguous | 0 | 25 |

There are 1,497 non-null scenario IDs and 12 non-null cohort IDs; 18,000 scenario IDs and 20,131 cohort IDs are null. Many families contain both classes, reinforcing the need to measure behavioural context. The README states that 25 hard positives are deliberately ambiguous payments with labels independent of observable features; do not manufacture a rule to identify them from hidden information.

## Payment structure and values

| Split | One leg | Two legs | Three legs | Conversion share | Median delivered USD | Maximum delivered USD |
|---|---:|---:|---:|---:|---:|---:|
| Train | 23,681 | 12,474 | 3,976 | 40.99% | 59.44 | 4,575.67 |
| Practice validation | 16,064 | 13,561 | 4,237 | 52.56% | 68.44 | 9,762.78 |
| Test | 19,840 | 15,351 | 4,910 | 50.52% | 49.98 | 9,592.97 |

Train median delivered value is USD 58.38 for ordinary payments and USD 86.52 for suspicious payments, with broad overlapping ranges. Amount alone does not establish a useful ranking model. Conversion frequencies and amount distributions differ between splits; evaluate reliance on these properties rather than assuming their stability.

## Checks and bundled starting point

All 12 training-package SHA-256 checksums match the supplied manifest. Test data has no supplied checksum manifest. Across all splits, assertions passed for unique transaction and leg keys, exact transfer coverage, block joins, consistent timestamps and ledger references, contiguous leg order, payment endpoints, delivered asset/value, XRP and IOU units, fees, finite positive leg values, rate-key uniqueness, complete price joins and payment-projection alignment. Labels have exact one-to-one training coverage and binary values.

`payments.py` successfully produces one sender-to-destination payment edge per transaction valued in reference USD. Its projected `VALUE` is USD and `SOURCE_VALUE` is micro-USD, unlike the raw transfer table; it replaces asset fields with a reference-valuation placeholder. Preserve raw spent/delivered assets separately when building richer features. Its no-rates fallback returns raw transfer legs; all current splits have rates, so that fallback is unused.

`starter_notebook.ipynb` was read, but not executed. It builds 12 amount, wallet activity, burst, forwarding and pass-through features; uses standardized balanced logistic regression; evaluates on a stratified 20% holdout with seed 0; and retrains for test scoring. Its default paths need adapting to this repository. There is no separate supplied `baseline.py`.

The actual README explicitly permits whole-window offline investigation, including later-within-week unlabeled graph activity. Keep graphs separate by split and keep held-out labels out of all predictive features and fitted target statistics. A random transaction holdout is a useful first diagnostic but can share graph/scenario context; supplement it with an evaluation that challenges generalization. Unlabelled `validation/` checks execution and distribution shift, but cannot produce local AP.

Next step: run a reproducible baseline with exact hash alignment and held-out AP, then assess additional wallet/temporal features using a consistent validation protocol. No model-quality claim follows from this audit.
