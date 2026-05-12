# Phase 1 L2Tree vs Baseline Summary

Configuration:

- dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit: `10_000_000` deltas
- depth: `10`
- repeats: `3`
- workloads: `replay_only`, `replay_periodic_query(q=100)`, `replay_periodic_query(q=1000)`

## Replay Comparison

| Workload | Baseline updates/s | L2Tree updates/s | Throughput gain | Baseline elapsed (s) | L2Tree elapsed (s) | Peak RSS baseline (MB) | Peak RSS L2Tree (MB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `replay_only` | 187590.01 | 241336.87 | 28.65% | 53.31 | 41.44 | 51.07 | 31.53 |
| `replay_periodic_query::q100` | 186151.56 | 237071.93 | 27.35% | 53.72 | 42.18 | 51.08 | 31.51 |
| `replay_periodic_query::q1000` | 187379.40 | 239531.16 | 27.83% | 53.37 | 41.75 | 51.06 | 31.54 |

## Criterion Microbench

| Case | Baseline mean (ns) | L2Tree mean (ns) | Improvement |
| --- | ---: | ---: | ---: |
| `update_existing_level` | 77.215 | 17.472 | 77.37% |
| `insert_new_level` | 261.086 | 73.719 | 71.76% |
| `delete_existing_level` | 206.198 | 79.425 | 61.48% |
| `best_bid_ask` | 19.448 | 16.535 | 14.98% |
| `top_10_query` | 106.096 | 75.924 | 28.44% |
