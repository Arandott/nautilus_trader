# Phase 0 Baseline Summary

- Generated at: 2026-03-23T14:09:23.602248+00:00
- Dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

## Replay Runner

| Mode | Runs | Avg elapsed (ns) | Avg updates/s | Avg query (ns) | Max query (ns) | Avg peak RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `parse_only` | 3 | 37145420624 | 269220.81 | 0 | 0 | 29218133 |
| `replay_only` | 3 | 54166744829 | 184617.34 | 0 | 0 | 53476010 |
| `replay_periodic_query_q100` | 3 | 55005624580 | 181800.11 | 3217 | 225100 | 53414570 |
| `replay_periodic_query_q1000` | 3 | 54244800138 | 184351.45 | 4909 | 23470 | 53437781 |
