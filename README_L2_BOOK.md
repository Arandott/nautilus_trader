# L2 Specialized Order Book Notes

This branch contains the L2_MBP specialized order book experiments used for the
CUFE undergraduate project. The main implementations are:

- `L2TreeBook`: price-level `BTreeMap<BookPrice, Quantity>` for the default
  engineering candidate.
- `L2VecBook`: sorted contiguous levels for top-k / factor-query workloads.
- `L2GridBook`: tick-indexed paged grid for dense/deep-book exploration.

The native `OrderBook(BookType::L2_MBP)` remains the baseline and correctness
oracle.

## Build prerequisites

From the repository root:

```bash
make install-debug
make build-debug
```

For Rust-only checks or benchmarks, the repository `rust-toolchain.toml` selects
the expected toolchain. The comparison helper also reads that file and runs
`cargo +<toolchain>` automatically when present.

## Performance tests

### 1. Microbenchmarks

Run the criterion microbenchmarks for baseline, tree, vec, and grid:

```bash
cargo bench -p nautilus-model --bench l2_book_baseline_criterion -- --noplot
```

Criterion writes raw outputs under `target/criterion/`. The benchmark covers:

- update existing level
- insert new level
- delete existing level
- best bid/ask
- top 10 query

### 2. Direct replay runner

The direct runner is `tardis-l2-baseline` in the Tardis adapter crate. It can run
parse-only, replay-only, and replay with periodic top-N queries.

```bash
cargo run -p nautilus-tardis --bin tardis-l2-baseline -- \
  --dataset /path/to/binance-futures_incremental_book_L2_BTCUSDT.csv.gz \
  --book l2tree \
  --mode replay_only \
  --depth 10 \
  --output /tmp/l2tree_replay_only.json
```

Periodic query example:

```bash
cargo run -p nautilus-tardis --bin tardis-l2-baseline -- \
  --dataset /path/to/binance-futures_incremental_book_L2_BTCUSDT.csv.gz \
  --book l2vec \
  --mode replay_periodic_query \
  --query-interval 100 \
  --depth 10 \
  --output /tmp/l2vec_q100.json
```

Useful runner options:

- `--book baseline|l2tree|l2vec|l2grid`
- `--mode parse_only|replay_only|replay_periodic_query`
- `--query-interval <N>` for periodic query mode
- `--depth <N>` for top-N query depth
- `--limit <N>` for a quick subset smoke run
- `--price-precision` and `--size-precision` when the dataset does not carry
  enough precision metadata

### 3. Full comparison helper

The project helper runs criterion plus repeated replay workloads and writes
`raw/`, `processed/`, and `summaries/` outputs.

```bash
python3 cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py \
  --dataset /path/to/binance-futures_incremental_book_L2_BTCUSDT.csv.gz \
  --output-root cufe_undergraduate_playground/results/comparisons/local_l2_books \
  --books baseline,l2tree,l2vec,l2grid \
  --repeats 3 \
  --depth 10 \
  --query-intervals 100,1000
```

For a fast smoke run:

```bash
python3 cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py \
  --dataset /path/to/binance-futures_incremental_book_L2_BTCUSDT.csv.gz \
  --output-root /tmp/l2_books_smoke \
  --books baseline,l2tree,l2vec,l2grid \
  --repeats 1 \
  --limit 100000 \
  --skip-criterion
```

The final recorded 10M comparison summary is in:

```text
cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/summaries/comparison_summary.md
```

## E2E and correctness checks

### Rust parity on Tardis sample CSV

These tests replay the Tardis sample CSV through the baseline and specialized
books, then compare best bid/ask, sizes, sequence, update count, and top levels.

```bash
cargo test -p nautilus-tardis --test l2_book_parity
cargo test -p nautilus-tardis --test l2_vec_book_parity
```

### Rust DataEngine/cache e2e

These cover managed L2 subscriptions and cache updates for the tree backend and
shadow-backend path:

```bash
cargo test -p nautilus-data --test engine \
  test_managed_l2_depth10_subscription_with_tree_backend_updates_cache

cargo test -p nautilus-data --test engine \
  test_managed_l2_deltas_subscription_with_tree_shadow_backend_updates_cache
```

### Python DataEngine e2e

After `make build-debug`, run the targeted Python DataEngine test:

```bash
pytest tests/unit_tests/data/test_engine.py \
  -k "tree_backend_updates_managed_book"
```

This verifies that a managed `OrderBookDepth10` subscription with
`params={"l2_book_backend": "tree"}` creates a tree-backed managed book and
updates best bid/ask from depth data.

### Python backtest / matching e2e

After `make build-debug`, run the matching-engine tree backend test:

```bash
pytest tests/unit_tests/backtest/test_matching_engine.py \
  -k "l2_tree_backend_depth10_feeds_market_order_matching"
```

This verifies that a tree-backed L2_MBP matching engine can consume depth10 data
and fill a market order at the book ask.

## Notes on data

Large replay benchmarks require a local Tardis/Binance Futures L2 delta CSV or
CSV.GZ. The helper script has a local default path from the original experiment
machine, but reproducible runs should pass `--dataset` explicitly.

Use `--limit` for smoke checks before launching the full 10M replay.
