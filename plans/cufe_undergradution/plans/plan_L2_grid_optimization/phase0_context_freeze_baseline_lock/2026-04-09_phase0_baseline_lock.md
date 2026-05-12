# Phase 0 Baseline Lock

Date: 2026-04-09

## Scope

This Phase 0 note freezes the current context before any new `L2GridBook` optimization work.

This phase does not rerun benchmarks. It records:

- what the current authoritative result set is
- what conclusion we should currently trust
- why the current evidence still does not kill the grid hypothesis
- which commands and result conventions later phases must treat as the baseline

## Context Read

Phase 0 was grounded in the following files:

- `plans/cufe_undergradution/plans/plan_L2_grid_optimization/plan/2026-04-09_l2_grid_optimization_agent_prompt.md`
- `cufe_undergraduate_playground/thesis/brainstorm/2026-04-09_l2_orderbook_engineering_status.md`
- `plans/cufe_undergradution/implementation/phase3/2026-03-24_phase3_l2gridbook_devlog.md`
- `cufe_undergraduate_playground/notes/phase3/2026-03-24_phase3_refresh_summary.md`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/runner_summary.json`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/criterion_summary.json`
- `crates/model/src/orderbook/l2_grid.rs`
- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`

## Workspace Snapshot

- Repository root: `/home/ubuntu/chenbaowen/nautilus_trader`
- Current HEAD at freeze time: `076fe374f769ab65654aa5d472f8970ae47607eb`
- Worktree status at freeze time: dirty

Important implication:

- this lock is an artifact-level baseline freeze, not a clean-commit release tag
- later phases should not assume the repository was clean when this note was written
- authoritative comparison status is defined by the result directory below, not by git cleanliness

## Current Authoritative Result Set

Until a later phase explicitly replaces it, the only authoritative comparison result set is:

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000`

Minimum persisted artifacts inside that directory:

- `processed/runner_summary.json`
- `processed/criterion_summary.json`
- `summaries/all_books_summary.md`

Configuration frozen by that directory:

- dataset: `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit: `10_000_000` deltas
- repeats: `3`
- depth: `10`
- books: `baseline,l2tree,l2vec,l2grid`
- workloads:
  - `replay_only`
  - `replay_periodic_query(q=100)`
  - `replay_periodic_query(q=1000)`

The high-signal numbers we should carry forward are:

| Metric | baseline | l2tree | l2vec | l2grid |
| --- | ---: | ---: | ---: | ---: |
| replay throughput (`replay_only`, updates/s) | 187590.01 | 241336.87 | 126391.43 | 182042.22 |
| peak RSS (`replay_only`, MB) | 51.07 | 31.53 | 31.14 | 248.86 |
| `insert_new_level` (ns) | 261.086 | 73.719 | 59.239 | 463.419 |
| `delete_existing_level` (ns) | 206.198 | 79.425 | 69.049 | 300.707 |
| `best_bid_ask` (ns) | 19.448 | 16.535 | 10.473 | 45.533 |

## Current Conclusion In Plain Language

### Role split across the four structures

- `baseline` is the general-purpose `OrderBook`; it still carries richer book semantics and therefore extra overhead for pure `L2_MBP` replay.
- `L2TreeBook` is the strongest current engineering default because it strips away most baseline baggage while keeping cheap ordered insert/delete semantics through per-level `BTreeMap`.
- `L2VecBook` is a useful counterexample: query locality is excellent, but middle insert/remove costs dominate under real replay.
- `L2GridBook` is the most research-oriented structure: it moves ordering to sparse pages and uses page-local bitmap scans, but the current implementation has not converted that design into replay wins.

### Why `L2TreeBook` is currently ahead

The best current explanation is a workload/structure fit story:

- it removes most baseline overhead without introducing heavy fixed-size page bodies
- it handles dynamic insert/delete much more naturally than `L2VecBook`
- it avoids the current `L2GridBook` page-management costs, sparse-page waste, and delete-best repair overhead
- in the present shallow workload family, that balance beats both the more general baseline and the more aggressive grid design

This is not a claim that `BTreeMap` is universally optimal. It is a claim that, under the currently measured replay mix, `L2TreeBook` has the best engineering trade-off.

### Why the current workload is not enough to declare the grid route dead

The current authoritative workload is still too narrow to falsify the user's core hypothesis.

What the current workload does cover well:

- real replay on one concrete BTCUSDT L2 dataset
- shallow read depth (`depth = 10`)
- periodic query pressure at `q=100` and `q=1000`
- apples-to-apples comparison across all four book variants

What it does not yet cover well:

- genuinely deep query depths such as `top_100`, `top_500`, `top_1000`
- long-lived wide books with hundreds or thousands of active levels
- dense contiguous tick regions where page-local scans might amortize well
- sparse-vs-dense occupancy as an explicit experimental dimension
- query-heavy deep-book maintenance mixes instead of shallow top-of-book style reads

The criterion benchmark also stays shallow by construction:

- it seeds `64` levels per side
- it measures `top_10_query`, not deeper traversal
- it isolates operation classes, but it does not tell us whether deep contiguous pages could help in realistic wide-book workloads

So the right Phase 0 conclusion is:

- `L2GridBook` is currently losing on the available evidence
- but the available evidence is still not aligned enough with the deep-book hypothesis to settle the research question

## Entry Points Locked For Later Phases

### Validation entry points

- `cargo test -p nautilus-model l2_grid --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo test -p nautilus-tardis --test l2_book_parity`

### Replay runner entry point

Runner binary:

- `cargo run -p nautilus-tardis --bin tardis-l2-baseline -- --dataset ... --book ... --mode ...`

Supported books:

- `baseline`
- `l2tree`
- `l2vec`
- `l2grid`

Supported replay modes:

- `replay_only`
- `replay_periodic_query`

### Comparison script entry point

The shared comparison script is:

- `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py`

The closest reproduction command for the current authoritative comparison is:

```bash
python3 cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py \
  --dataset /home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz \
  --books baseline,l2tree,l2vec,l2grid \
  --repeats 3 \
  --depth 10 \
  --limit 10000000 \
  --modes replay_only,replay_periodic_query \
  --query-intervals 100,1000 \
  --output-root cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000
```

Note:

- the script currently writes `criterion_estimates.json` by default
- the frozen authoritative directory in the repo currently contains `criterion_summary.json`
- later phases must keep the naming convention explicit when replacing the authoritative directory instead of silently drifting between file names

## Authoritative Replacement Rules

The current authoritative result directory may be replaced only when all of the following are true:

1. The replacement is a single explicitly named comparison directory, not a pile of ad hoc smoke results.
2. It includes all four books: `baseline`, `l2tree`, `l2vec`, `l2grid`.
3. It includes both replay results and criterion results.
4. It persists at least:
   - `processed/runner_summary.json`
   - one criterion summary artifact with stable naming
   - a human-readable summary markdown
5. The producing phase also records:
   - exact command(s)
   - workload parameters
   - why this directory supersedes the prior one
6. A later note explicitly says the previous authoritative directory is superseded.

Directories that do not satisfy those conditions should be treated as:

- smoke results
- exploratory results
- single-issue diagnostics

They are useful, but they are not authoritative.

## Open Questions Handed To Phase 1

Phase 0 does not answer these yet, but it freezes them as the next mandatory questions:

- how large is a `GridPage` in bytes under the current representation
- how sparse or dense are active pages under real replay
- whether the main replay pain is page footprint, page index cost, delete-best repair, or page-local traversal
- whether `PAGE_SIZE = 64` is materially misaligned with the observed occupancy pattern

## Phase 0 Exit Criteria Check

- Current authoritative result directory identified: yes
- Current most credible conclusion restated in plain language: yes
- Why `L2TreeBook` currently leads explained: yes
- Why current workloads still do not settle the deep-book hypothesis explained: yes
- Replay / criterion / parity entry points recorded: yes
- Rule for replacing the authoritative baseline recorded: yes

Phase 0 is complete once later phases use this note as the only baseline reference point unless they explicitly supersede it.
