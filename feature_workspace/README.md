# Feature preparation workspace

Keep feature preparation separate from the supplied datasets and the verified baseline.

- Python feature modules belong in this package; exploratory notebooks belong in `notebooks/`.
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

No feature extraction, source-data copies or model training is performed by this setup. Source files and their filesystem permissions are unchanged. The measured baseline stays in `scripts/baseline.py` and `outputs/baseline_wallet_seed0/`.
