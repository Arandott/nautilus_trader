# L2 Book Comparison Summary

- Generated at: 2026-04-10T07:30:31.089705+00:00
- Dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- Books: `baseline, l2tree, l2vec, l2grid`

## Criterion

| Book | Case | Mean point estimate | Median point estimate |
| --- | --- | ---: | ---: |
| `baseline` | `update_existing_level` | 75.43352192151268 | 75.37793915937189 |
| `baseline` | `insert_new_level` | 262.52312766578876 | 261.4710716747071 |
| `baseline` | `delete_existing_level` | 211.58043407913024 | 211.1820993776955 |
| `baseline` | `best_bid_ask` | 20.286705903348473 | 19.605072026134447 |
| `baseline` | `top_10_query` | 109.09268132451555 | 108.80045571396744 |
| `l2tree` | `update_existing_level` | 18.571688731994445 | 18.454061536732738 |
| `l2tree` | `insert_new_level` | 74.5743879279937 | 74.09808021064373 |
| `l2tree` | `delete_existing_level` | 81.3004440380586 | 81.0938813621384 |
| `l2tree` | `best_bid_ask` | 17.87703812179111 | 17.805827673615372 |
| `l2tree` | `top_10_query` | 77.69927903281842 | 77.16637297016491 |
| `l2vec` | `update_existing_level` | 25.796079968778812 | 26.134072602631456 |
| `l2vec` | `insert_new_level` | 62.790786241270915 | 62.87176738320696 |
| `l2vec` | `delete_existing_level` | 66.39719619510826 | 66.97208109653735 |
| `l2vec` | `best_bid_ask` | 32.81831347323207 | 32.631033294091665 |
| `l2vec` | `top_10_query` | 18.24693678080132 | 18.183692406932636 |
| `l2grid` | `update_existing_level` | 33.90319232195895 | 33.793958311937836 |
| `l2grid` | `insert_new_level` | 362.32952636795056 | 360.75756897081027 |
| `l2grid` | `delete_existing_level` | 244.80266078949487 | 244.6998687835677 |
| `l2grid` | `best_bid_ask` | 57.51270752479921 | 57.16139449771236 |
| `l2grid` | `top_10_query` | 208.0637060164024 | 206.4936333512793 |

## Replay Runner

| Key | Runs | Avg elapsed (ns) | Avg updates/s | Avg query (ns) | Max query (ns) | Avg peak RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline::replay_only` | 3 | 53609787053 | 186535.20 | 0 | 0 | 54616064 |
| `baseline::replay_periodic_query::q100` | 3 | 54114552763 | 184806.10 | 3379 | 45230 | 54624256 |
| `baseline::replay_periodic_query::q1000` | 3 | 54013166733 | 185140.38 | 5354 | 26550 | 54618794 |
| `l2grid::replay_only` | 3 | 52627038868 | 190025.20 | 0 | 0 | 216199168 |
| `l2grid::replay_periodic_query::q100` | 3 | 52856031579 | 189194.93 | 4554 | 145311 | 215972522 |
| `l2grid::replay_periodic_query::q1000` | 3 | 53210403290 | 187935.21 | 6249 | 30475 | 215902890 |
| `l2tree::replay_only` | 3 | 41753711599 | 239499.86 | 0 | 0 | 34177024 |
| `l2tree::replay_periodic_query::q100` | 3 | 42404617816 | 235823.59 | 2139 | 30296 | 34112853 |
| `l2tree::replay_periodic_query::q1000` | 3 | 42148177792 | 237262.84 | 2605 | 21311 | 34104661 |
| `l2vec::replay_only` | 3 | 56963721235 | 175552.72 | 0 | 0 | 32146773 |
| `l2vec::replay_periodic_query::q100` | 3 | 57396310174 | 174228.36 | 757 | 21745 | 32126293 |
| `l2vec::replay_periodic_query::q1000` | 3 | 57139310655 | 175013.03 | 1299 | 17417 | 32146773 |
