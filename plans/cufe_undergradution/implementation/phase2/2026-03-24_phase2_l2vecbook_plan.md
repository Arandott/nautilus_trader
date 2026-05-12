# Phase 2 Plan: `L2VecBook`

## Goal

Implement a full Rust-only `L2VecBook` to test whether a
price-level-specialized, contiguous layout can outperform `L2TreeBook` on
update-heavy and replay-heavy L2 workloads.

This phase should answer:

- Does contiguous storage improve locality enough to beat `BTreeMap`?
- What is the tradeoff between faster scans and more expensive inserts/deletes?
- On real replay, is `L2VecBook` better, worse, or workload-dependent?

## Scope

In scope:

- new `L2VecBook` implementation
- `L2BookOps` conformance
- parity tests against baseline
- criterion integration
- replay runner integration through `--book l2vec`

Out of scope:

- changing `L2BookOps`
- changing workload definitions
- optimizing Python paths
- persistence changes

## Proposed Data Structure

Recommended first implementation:

- `bids: Vec<(Price, Quantity)>`
- `asks: Vec<(Price, Quantity)>`

Recommended ordering:

- bids sorted descending by price
- asks sorted ascending by price

Recommended baseline operations:

- search with `binary_search_by`
- update in place when level exists
- insert by shifting tail when level is new
- delete by removing exact index
- clear both sides on `Clear`

The first version should prefer simplicity and correctness over aggressive
auxiliary indexing.

## Expected Gains

Main hypotheses:

- `best_bid_ask` should remain very fast because best levels are at the head
- `top_n_levels` should be strong due to contiguous memory
- replay performance may improve if the L2 book stays shallow enough

Main risks:

- repeated inserts/deletes can be expensive because elements shift
- deep books with many mid-book changes may reduce the gain

## Implementation Plan

1. Add `crates/model/src/orderbook/l2_vec.rs`
2. Implement `L2VecBook`
3. Reuse the same metadata policy as `L2TreeBook`
4. Implement `L2BookOps`
5. Export type from `crates/model/src/orderbook/mod.rs`
6. Extend replay runner `BookKind` with `l2vec`
7. Extend criterion bench with `l2vec_*` cases
8. Add parity tests against baseline and `L2TreeBook`

## Required Invariants

- one level per `(side, price)`
- bids remain strictly ordered descending
- asks remain strictly ordered ascending
- zero-size levels must not remain stored
- `sequence` and `ts_last` must advance with the same policy as `L2TreeBook`

## Test Plan

Unit tests:

- insert into empty side
- update existing level
- insert at head, middle, tail
- delete head, middle, tail
- clear book

Parity tests:

- synthetic sequences already used for `L2TreeBook`
- small Tardis CSV replay parity

Bench and workload:

- all five criterion cases
- `replay_only`
- `replay_periodic_query(q=100)`
- `replay_periodic_query(q=1000)`

## Acceptance Criteria

The phase is complete when:

- `L2VecBook` passes parity tests
- it integrates into the shared bench and replay harness
- it produces a stable measurement set under the same config used in Phase 1
- an implementation note is written describing observed strengths and
  weaknesses

## File Change Budget

Primary owned file:

- `crates/model/src/orderbook/l2_vec.rs`

Expected additive shared changes:

- `crates/model/src/orderbook/mod.rs`
- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`

Avoid touching:

- baseline result directories
- correctness/workload specifications
- Python package code
