# Phase 0 Baseline Summary

- Generated at: 2026-03-23T13:36:15.184796+00:00
- Dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

## Replay Runner

| Mode | Runs | Avg elapsed (ns) | Avg updates/s | Avg query (ns) | Max query (ns) | Avg peak RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `parse_only` | 1 | 37505811497 | 266625.35 | 0 | 0 | 29200384 |
| `replay_only` | 1 | 54544488646 | 183336.58 | 0 | 0 | 53411840 |
| `replay_periodic_query_q1000` | 1 | 53966027265 | 185301.76 | 4926 | 25222 | 53460992 |
