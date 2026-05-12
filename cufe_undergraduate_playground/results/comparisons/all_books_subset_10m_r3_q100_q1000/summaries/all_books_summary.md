# All Books Comparison Summary

Configuration:

- dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit: `10_000_000` deltas
- depth: `10`
- repeats: `3`
- workloads: `replay_only`, `replay_periodic_query(q=100)`, `replay_periodic_query(q=1000)`

## Replay Throughput

| Workload | baseline updates/s | l2tree updates/s | l2vec updates/s | l2grid updates/s |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 187590.01 | 241336.87 | 126391.43 | 182042.22 |
| `replay_periodic_query::q100` | 186151.56 | 237071.93 | 127102.13 | 181103.72 |
| `replay_periodic_query::q1000` | 187379.40 | 239531.16 | 127536.53 | 182292.63 |

## Replay Elapsed Time

| Workload | baseline (s) | l2tree (s) | l2vec (s) | l2grid (s) |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 53.31 | 41.44 | 79.12 | 54.93 |
| `replay_periodic_query::q100` | 53.72 | 42.18 | 78.68 | 55.22 |
| `replay_periodic_query::q1000` | 53.37 | 41.75 | 78.41 | 54.86 |

## Peak RSS

| Workload | baseline (MB) | l2tree (MB) | l2vec (MB) | l2grid (MB) |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 51.07 | 31.53 | 31.14 | 248.86 |
| `replay_periodic_query::q100` | 51.08 | 31.51 | 31.14 | 248.97 |
| `replay_periodic_query::q1000` | 51.06 | 31.54 | 31.24 | 248.73 |

## Criterion Means

| Case | baseline (ns) | l2tree (ns) | l2vec (ns) | l2grid (ns) |
| --- | ---: | ---: | ---: | ---: |
| `update_existing_level` | 77.215 | 17.472 | 28.450 | 31.366 |
| `insert_new_level` | 261.086 | 73.719 | 59.239 | 463.419 |
| `delete_existing_level` | 206.198 | 79.425 | 69.049 | 300.707 |
| `best_bid_ask` | 19.448 | 16.535 | 10.473 | 45.533 |
| `top_10_query` | 106.096 | 75.924 | 18.465 | 96.162 |
