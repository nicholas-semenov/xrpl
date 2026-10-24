# Wallet transaction graphs

Command: `.venv/bin/python -m feature_workspace.build_wallet_graph`

Three separate directed multigraphs; node = wallet, edge/key = transaction hash, direction = SENDER → RECEIVER. All 15 prepared columns are retained without aggregation or numeric conversion. Full seven-day histories are used. No labels, conversion legs, AML pattern IDs or model fitting are involved.

| Split | Nodes | Edges | Senders | Receivers | Directed pairs | Both directions | Incoming only |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 700 | 40,131 | 676 | 700 | 22,315 | 676 | 24 |
| validation | 700 | 33,862 | 676 | 700 | 18,773 | 676 | 24 |
| test | 700 | 40,101 | 676 | 700 | 22,557 | 676 | 24 |

| Split | Incoming USD (delivered) | Outgoing USD (spent) | Extra parallel edges | Self-loops |
|---|---:|---:|---:|---:|
| train | 5,677,308.097102 | 5,684,000.818105 | 17,816 | 0 |
| validation | 5,202,975.393174 | 5,215,014.360740 | 15,089 | 0 |
| test | 5,580,437.289433 | 5,591,795.039585 | 17,544 | 0 |

Incoming volume uses DESTINATION_AMOUNT_USD; outgoing uses SOURCE_AMOUNT_USD. These valuations differ for conversions because of reference prices and executed quotes/spreads. Network fees remain a separate XRP attribute; no fee edges or leg-value sums are added.

IN_DEGREE/OUT_DEGREE count transaction edges, including repeated wallet pairs. UNIQUE_IN_NEIGHBORS/UNIQUE_OUT_NEIGHBORS count distinct counterparties. TRANSACTION_COUNT counts distinct incident transactions; a self-loop counts once here and once in each directional degree. Statistics include zero-degree wallets; standard deviations are population values.


## train

Observed events: 2026-09-01 00:05:44+00:00 through 2026-09-07 23:58:00+00:00.

| Statistic | Min | Mean | Median | 95th percentile | Max |
|---|---:|---:|---:|---:|---:|
| IN_DEGREE | 14 | 57.3300 | 51.0 | 105.05 | 256 |
| OUT_DEGREE | 0 | 57.3300 | 56.0 | 93.00 | 216 |
| UNIQUE_IN_NEIGHBORS | 11 | 31.8786 | 30.0 | 52.25 | 90 |
| UNIQUE_OUT_NEIGHBORS | 0 | 31.8786 | 31.0 | 50.00 | 180 |
| TRANSACTION_COUNT | 43 | 114.6600 | 110.0 | 179.20 | 314 |

| Incident transactions per wallet | Wallets |
|---|---:|
| 0 | 0 |
| 1 | 0 |
| 2-5 | 0 |
| 6-10 | 0 |
| 11-25 | 0 |
| 26-50 | 7 |
| 51-100 | 264 |
| 101-250 | 420 |
| 251-500 | 9 |
| 501+ | 0 |

## validation

Observed events: 2026-09-10 00:04:24+00:00 through 2026-09-16 23:48:04+00:00.

| Statistic | Min | Mean | Median | 95th percentile | Max |
|---|---:|---:|---:|---:|---:|
| IN_DEGREE | 11 | 48.3743 | 45.0 | 88.05 | 150 |
| OUT_DEGREE | 0 | 48.3743 | 47.0 | 80.00 | 151 |
| UNIQUE_IN_NEIGHBORS | 7 | 26.8186 | 25.0 | 45.10 | 68 |
| UNIQUE_OUT_NEIGHBORS | 0 | 26.8186 | 25.0 | 44.00 | 136 |
| TRANSACTION_COUNT | 28 | 96.7486 | 93.0 | 148.00 | 202 |

| Incident transactions per wallet | Wallets |
|---|---:|
| 0 | 0 |
| 1 | 0 |
| 2-5 | 0 |
| 6-10 | 0 |
| 11-25 | 0 |
| 26-50 | 29 |
| 51-100 | 376 |
| 101-250 | 295 |
| 251-500 | 0 |
| 501+ | 0 |

## test

Observed events: 2026-09-20 00:06:36+00:00 through 2026-09-26 23:59:32+00:00.

| Statistic | Min | Mean | Median | 95th percentile | Max |
|---|---:|---:|---:|---:|---:|
| IN_DEGREE | 14 | 57.2871 | 50.0 | 107.00 | 223 |
| OUT_DEGREE | 0 | 57.2871 | 55.0 | 95.00 | 215 |
| UNIQUE_IN_NEIGHBORS | 11 | 32.2243 | 29.0 | 54.05 | 98 |
| UNIQUE_OUT_NEIGHBORS | 0 | 32.2243 | 30.0 | 50.00 | 182 |
| TRANSACTION_COUNT | 37 | 114.5743 | 108.5 | 183.00 | 316 |

| Incident transactions per wallet | Wallets |
|---|---:|
| 0 | 0 |
| 1 | 0 |
| 2-5 | 0 |
| 6-10 | 0 |
| 11-25 | 0 |
| 26-50 | 4 |
| 51-100 | 279 |
| 101-250 | 409 |
| 251-500 | 8 |
| 501+ | 0 |

Exact degree/count histograms, full precision volumes, checks and artifact hashes are in wallet_graphs.json. Per-wallet statistics are stored in nodes.parquet. Raw and prepared inputs remain unchanged. Original hashes/directions/timestamps and every prepared edge attribute were checked.

Edges are sorted by (TIMESTAMP, TRANSACTION_HASH); this order is also used by incoming/outgoing adjacency queries. Hash ordering only resolves timestamp ties deterministically, not causally. For a strictly later hop use outgoing(wallet, after=previous_timestamp). No path detector is implemented.

Cross-split wallet/hash intersections are zero. All graph artifacts were reloaded and rebuilt identically. No integrity issues were discovered. Incoming-only wallets and parallel payments are retained.
