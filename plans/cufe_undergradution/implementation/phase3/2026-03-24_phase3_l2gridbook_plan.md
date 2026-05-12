# Phase 3 Plan: `L2GridBook`

## Goal

Implement a Rust-only `L2GridBook` that is genuinely more grid-like than
`L2TreeBook`. The core objective is no longer just "tick-keyed storage"; it is
to reduce or remove tree-based overhead by using a chunked sparse-array layout
with bitmap-assisted active-level tracking.

This phase should answer:

- Can a non-tree grid layout outperform `L2TreeBook` on replay-heavy L2
  workloads?
- Which baseline overheads are specifically reduced by chunked grid storage?
- What trade-offs are introduced by page allocation, bitmap maintenance, and
  best-pointer repair?

## Scope

In scope:

- a full Rust-only `L2GridBook` implementation
- `L2BookOps` conformance
- parity tests against baseline
- criterion integration
- replay runner integration through `--book l2grid`
- an implementation note describing layout, invariants, and trade-offs

Out of scope:

- changing `L2BookOps`
- redesigning persistence
- Python/FFI integration
- broad refactors of the benchmark harness

## Design Position

The existing `L2GridBook` prototype validated grid semantics, but it still uses
`BTreeMap<tick, level>` as its primary storage. That makes it a sparse
tick-indexed prototype, not a fully realized grid engine.

Phase 3 should therefore move from:

- sparse `BTreeMap` keyed by `Price::raw`

to:

- sparse page index
- fixed-size per-page arrays
- bitmap-assisted occupancy tracking
- explicit best tick / best page maintenance

The target is a hybrid structure that is sparse globally but dense locally.

## Proposed Data Structure

Recommended mainline design: **chunked sparse array + bitmap**.

Per side:

- `pages: HashMap<PageId, GridPage>` or `BTreeMap<PageId, GridPage>`
- `best_tick: Option<PriceTick>`
- `best_page: Option<PageId>`

Per page:

- `base_tick: PriceTick`
- `levels: [Option<GridLevel>; PAGE_SIZE]` or equivalent compact slot storage
- `occupancy_bitmap: u64` or multiple `u64`s when `PAGE_SIZE > 64`
- optional `active_count`

Indexing:

- `tick = price.raw`
- `page_id = floor_div(tick, PAGE_SIZE)`
- `slot = mod_floor(tick, PAGE_SIZE)`

Recommended starting constant:

- `PAGE_SIZE = 64` or `128`

This layout keeps global storage sparse while making local access O(1)-like
within a page.

## Why This Structure

This design specifically targets the overheads we already identified:

- reduce tree-node traversal and comparison costs present in `L2TreeBook`
- avoid the middle-element shifting cost that hurts `L2VecBook`
- preserve L2-native `price -> level` semantics
- support stronger best-level and top-N traversal via bitmap scans

In other words, the grid path should now be justified as:

- **Baseline** removes generic order semantics poorly for L2
- **L2TreeBook** removes generic order semantics cleanly
- **L2GridBook** aims to remove remaining tree-comparison overhead on top of
  `L2TreeBook`

## Expected Gains

Main hypotheses:

- page-local upsert/delete will be cheaper than tree-node operations once the
  page is located
- best bid / ask maintenance can become cheaper through explicit page and tick
  tracking
- top-N can benefit from page-local bitmap scans over active slots
- replay throughput may improve when active levels cluster in a small number of
  nearby pages

Expected trade-offs:

- more complex implementation than both `L2TreeBook` and `L2VecBook`
- delete-best handling is harder because it may require bitmap scan and
  cross-page fallback
- sparse global page indexing may still need ordered lookup depending on page
  container choice
- page size tuning becomes a real design variable

## Design Variants

The preferred route is:

1. sparse ordered page index + fixed-size page arrays + bitmap
2. if needed later, move page index from ordered map toward hash index plus
   explicit best-page tracking

Not recommended as the main Phase 3 route:

- full dense array across the whole price range
- sliding-window-only grid
- staying on `BTreeMap<tick, level>` and calling that "grid"

## Implementation Plan

1. Refactor `crates/model/src/orderbook/l2_grid.rs` from sparse-tree prototype
   into chunked sparse-array storage.
2. Define page ID / slot math from `Price::raw`.
3. Implement page-local `upsert`, `delete`, `clear`, and bitmap maintenance.
4. Implement best tick / best page repair logic after deletes.
5. Implement `top_n_levels` by page traversal plus in-page bitmap scan.
6. Preserve metadata behavior required by `L2BookOps`.
7. Keep shared runner and benchmark integration through existing `--book l2grid`.
8. Add parity tests and structure-specific stress tests.
9. Run the shared replay workloads under the same config as Phase 1.

## Required Design Decisions

These must be written down in the implementation note:

- how `Price::raw` maps to `(page_id, slot)`
- chosen `PAGE_SIZE` and why
- whether page index is `HashMap`, `BTreeMap`, or hybrid
- how empty pages are reclaimed
- how best bid / ask fallback works when the best slot is deleted
- how top-N traverses pages and slots
- whether bitmap scans use `trailing_zeros` / `leading_zeros` style operations

## Required Invariants

- one level per `(side, price)`
- no stale best-pointer after delete
- no retained zero-size levels
- tick conversion must be deterministic
- empty pages must not remain live unless explicitly justified
- page bitmap and slot storage must always agree
- metadata updates must match the shared policy used by `L2TreeBook`

## Test Plan

Unit tests:

- tick to `(page_id, slot)` conversion correctness
- insert/update/delete at the same slot
- delete best level and best-pointer fallback within page
- delete best level and best-pointer fallback across pages
- clear book
- sparse wide-gap page allocation and reclamation
- bitmap and slot consistency

Parity tests:

- synthetic delta sequences
- small Tardis CSV replay parity

Bench and workload:

- all five criterion cases
- `replay_only`
- `replay_periodic_query(q=100)`
- `replay_periodic_query(q=1000)`

Additive stress tests are encouraged for:

- wide sparse ranges
- concentrated active pages
- repeated best-level deletion

## Acceptance Criteria

The phase is complete when:

- `L2GridBook` passes parity tests
- it runs under the shared bench and replay harness
- a complete measurement set exists under the same config as Phase 1
- the implementation note clearly explains what overheads were targeted, what
  trade-offs were introduced, and which hypotheses were validated
- the final implementation is no longer primarily a `BTreeMap<tick, level>`
  design

## File Change Budget

Primary owned file:

- `crates/model/src/orderbook/l2_grid.rs`

Expected additive shared changes:

- `crates/model/src/orderbook/mod.rs`
- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`

Avoid touching:

- baseline and Phase 1 result directories
- workload/correctness specification files
- Python-facing code
