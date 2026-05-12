# Parallel Development Contract for Phase 2 and Phase 3

## Purpose

This document defines the shared boundaries for parallel implementation of:

- `Phase 2`: `L2VecBook`
- `Phase 3`: `L2GridBook`

The goal is to let two agents work independently without conflicting on the
benchmark harness, correctness rules, or output schema already established by
Phase 0 and Phase 1.

## Frozen Shared Surface

These interfaces and workflows should be treated as frozen unless both plans
explicitly require the same change:

- `L2BookOps` in `crates/model/src/orderbook/l2.rs`
- `tardis-l2-baseline` CLI contract in
  `crates/adapters/tardis/bin/l2_baseline.rs`
- Criterion benchmark structure in
  `crates/model/benches/l2_book_baseline_criterion.rs`
- Correctness rules in
  `plans/cufe_undergradution/correctness/correctness_spec.md`
- Workload definitions in
  `plans/cufe_undergradution/workloads/workload_spec.md`

Shared expectations:

- Input stays `OrderBookDelta` / `OrderBookDeltas`
- Existing `baseline` and `l2tree` behavior must remain unchanged
- Output JSON field names from the replay runner must remain stable
- Existing Phase 0 and Phase 1 result directories remain untouched

## Acceptable Shared Changes

The following are allowed if done carefully and backwards-compatibly:

- Extend the `BookKind` enum in `l2_baseline.rs`
- Register new benchmark cases in `l2_book_baseline_criterion.rs`
- Export new types from `crates/model/src/orderbook/mod.rs`
- Add new crate-local tests

Rule: any shared change must be additive, not a rewrite.

## File Ownership

### Shared files

These files may be touched by both implementations, but only in small additive
ways:

- `crates/model/src/orderbook/mod.rs`
- `crates/model/src/orderbook/l2.rs`
- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`

### Phase 2 owned files

- `crates/model/src/orderbook/l2_vec.rs`
- `crates/model/tests` or crate-local tests for `L2VecBook`
- Optional parity test file for `L2VecBook`

### Phase 3 owned files

- `crates/model/src/orderbook/l2_grid.rs`
- `crates/model/tests` or crate-local tests for `L2GridBook`
- Optional parity test file for `L2GridBook`

## Shared Validation Standard

Both implementations must satisfy the same checks before workload comparison:

- `best_bid_price`, `best_ask_price`
- `best_bid_size`, `best_ask_size`
- sampled `top_n_levels` equality
- replay final state parity on the small Tardis sample
- metadata parity where meaningful:
  `sequence`, `ts_last`, `update_count`

## Output Expectations

Each phase should produce:

- implementation code
- unit tests
- parity tests against baseline
- bench integration
- replay runner integration
- one concise implementation note describing the chosen data structure,
  invariants, and expected gains

## Recommended Execution Order

1. Keep the shared contract fixed
2. Implement the phase-local book type
3. Add phase-local tests
4. Add additive registration in bench and runner
5. Run parity checks
6. Run the existing Phase 1 workload configuration

## Non-Goals

The following are out of scope for both phases:

- Python bindings
- FFI exposure
- data engine integration
- persistence format redesign
- changing workload definitions mid-phase
