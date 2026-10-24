# AML patterns 1–4: descriptive detections

Command: `.venv/bin/python -m feature_workspace.prepare_aml_features`

IDs: 1 fan-in; 2 fan-out; 3 scatter-gather; 4 gather-scatter. Membership is not a suspicion label or probability. No labels/annotation files were read and no model was trained.

| Split | Transactions | ID 1 | ID 2 | ID 3 | ID 4 | Any pattern | Multiple patterns |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 40,131 | 40,131 | 40,131 | 15,607 | 39,800 | 40,131 | 40,131 |
| validation | 33,862 | 33,862 | 33,862 | 7,743 | 33,647 | 33,862 | 33,862 |
| test | 40,101 | 40,101 | 40,101 | 12,113 | 39,796 | 40,101 | 40,101 |

Counts above are unions across windows; per-pattern counts overlap and must not be summed.

| Split | Window | ID 1 | ID 2 | ID 3 | ID 4 |
|---|---|---:|---:|---:|---:|
| train | 1h | 16,011 | 14,176 | 326 | 266 |
| train | 24h | 40,082 | 40,114 | 631 | 35,951 |
| train | 7d | 40,131 | 40,131 | 15,602 | 39,778 |
| validation | 1h | 12,447 | 11,034 | 282 | 169 |
| validation | 24h | 33,781 | 33,804 | 454 | 29,406 |
| validation | 7d | 33,862 | 33,862 | 7,743 | 33,632 |
| test | 1h | 15,594 | 14,896 | 312 | 287 |
| test | 24h | 40,030 | 40,056 | 579 | 35,989 |
| test | 7d | 40,101 | 40,101 | 12,106 | 39,780 |

Each output has 133 columns: original 15, aml_pattern (list<int8>), and 117 numerical AML features. Original transaction order, hash coverage, field values and types were preserved. Parquet artifacts were read back and checked.

Default thresholds and exact definitions are in feature_workspace/AML_PATTERNS.md and aml_thresholds.json. The feature schema separates numeric/categorical model inputs from identifiers and list metadata. The seven-day motifs are broad structural descriptions and can include legitimate hubs; counts do not establish detector precision/recall. No performance claim or threshold tuning against targets was made.

Strict temporal paths use first timestamp < second timestamp. All witness events fit inside their specified total window span. USD flow sums deduplicate transaction IDs; two-hop path counts preserve distinct event pairs. Self-payments remain in output but do not supply motif evidence. Bounds at the dataset start/end use only observed events and may truncate history.

Resource counters, timings, input/output/code hashes, witness counts and window-specific detections are in aml_patterns.json. Limits fail explicitly without sampling or silent truncation. All datasets use the same fixed configuration and remain separate.
