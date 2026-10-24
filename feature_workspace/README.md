# Feature preparation workspace

Keep feature preparation separate from the supplied datasets and the verified baseline.

- Python feature modules belong in this package. The unused `notebooks/` directory was removed.
- Intermediate tables, feature matrices and experiment outputs belong in `generated/`. Its contents are ignored by Git, apart from the directory placeholder.
- Source training inputs remain at `../data/traning_data/train/`. Open source files for reading only; write derived data under `generated/`. Do not overwrite, move or rename source files.
- `paths.py` exposes `TRAIN_INPUT` and `output_path(relative_filename)`. The output helper rejects absolute paths, parent traversal outside `generated/`, and existing symlinks that lead outside it. Future feature writers must use the helper; it does not prevent unrelated code from opening arbitrary paths.
- Keep `TRANSACTION_HASH` as an alignment key. Do not use labels, family, difficulty, scenario/cohort IDs or raw identifiers as predictive features. Preserve the baseline's split isolation in feature experiments.

Example paths, run from the repository root:

```python
from feature_workspace.paths import TRAIN_INPUT, output_path

input_file = TRAIN_INPUT / "transactions.parquet"
feature_file = output_path("train_features.parquet")
# Read input_file; save the derived feature table to feature_file.
```

## Transaction preparation

From the repository root, using the dependencies in `requirements-baseline.txt`:

```sh
.venv/bin/python -m feature_workspace.prepare_transactions
.venv/bin/python -m unittest discover -s tests -v
```

The command separately reads transactions, transfers and market rates from train, practice validation and test. No labels or annotation metadata are read. Original files and permissions are unchanged. The measured baseline stays in `scripts/baseline.py` and `outputs/baseline_wallet_seed0/`; it is not retrained.

Outputs for each split are under `generated/transaction_tables_v1/{train,validation,test}/`:

- `transactions.parquet`: exactly one row per original transaction, in its original order, containing the 15 columns below.
- `transfer_legs.parquet`: all original detailed transfer records and their Arrow column types, sorted by `(TRANSACTION_HASH, TRANSFER_INDEX)`.

`generated/transaction_tables_v1/summary.json` and the aggregate reports `../reports/transaction_preparation.json` / `.md` contain counts, step distributions, top ten asset pairs (all payments and conversions separately), sample calculations, integrity checks and source/output hashes.

| Column | Definition |
|---|---|
| `TRANSACTION_HASH` | Original transaction key; never a predictive measurement |
| `TIMESTAMP` | Original Unix timestamp, integral seconds |
| `SENDER` | Transaction `ACCOUNT`, checked against the first leg |
| `RECEIVER` | JSON `EXTRA_TRANSACTION_FIELDS.Destination`, checked against the last leg |
| `SOURCE_ASSET` | First leg's `XRP` or `issuer:currency` identity |
| `SOURCE_AMOUNT` | Actual first-leg amount in whole XRP/token units |
| `DESTINATION_ASSET` | Last leg's full asset identity |
| `DESTINATION_AMOUNT` | Actual last-leg amount in whole units, checked against delivered JSON |
| `SOURCE_AMOUNT_USD` | Source amount × source asset's hourly reference price |
| `DESTINATION_AMOUNT_USD` | Destination amount × destination asset's hourly reference price |
| `TRANSFER_COUNT` | Number of executed legs |
| `IS_CONVERSION` | Whether any adjacent full asset identity changes |
| `CONVERSION_STEP_COUNT` | Number of adjacent asset identity changes, including issuer changes |
| `INTERMEDIARY_COUNT` | Number of distinct path addresses excluding the original sender and final receiver |
| `FEE_XRP` | Burned network fee, separately normalized from `SOURCE_FEE` drops |

`VALUE` is verified against `SOURCE_VALUE`: XRP `SOURCE_VALUE / 1,000,000 = VALUE`; IOU `SOURCE_VALUE = VALUE`. Amounts use already-normalized `VALUE` without dividing again. Source and destination prices use their own asset identities at `TIMESTAMP // 3600 * 3600`; each `PRICE_MICRO_USD` is divided by 1,000,000. Missing/duplicate rates and inconsistent units fail instead of being guessed. USD leg values are never summed; `SendMax` is never used as spending. Floating values retain input precision without intentional rounding; numeric comparisons allow only floating-point tolerance.

Conversion count is independent of transfer count: same-asset extra legs count as zero changes; `A → B → A` counts as two changes despite equal endpoint assets. These cases are tested even though every adjacent leg in the supplied splits changes asset. Intermediaries in the current conversions are liquidity providers, not evidence of AML layering.

Checks cover unique keys, exact leg coverage, matching ledger metadata, contiguous indices, continuous executed paths, endpoints, delivered JSON, units, fees, hourly price coverage, and finite outputs. Every destination USD value is cross-checked against the supplied `payments.py`. Both output Parquet tables are read back and compared. Existing tables with different content are refused: use a new `--run-name transaction_tables_v2` for future changed definitions.

These transaction-local fields do not learn statistics from other rows. When adding wallet-history features later, retain split isolation from the baseline and never combine synthetic worlds.
