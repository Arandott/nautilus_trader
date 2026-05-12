# Phase 2 Agent Prompt

You are implementing `Phase 2: L2VecBook` in the NautilusTrader workspace.

Read these files first:

- `plans/cufe_undergradution/implementation/shared/2026-03-24_parallel_development_contract.md`
- `plans/cufe_undergradution/implementation/phase2/2026-03-24_phase2_l2vecbook_plan.md`

Current context:

- `Phase 0` baseline and `Phase 1` `L2TreeBook` are complete.
- The shared boundary is already wired for `baseline`, `l2tree`, `l2vec`, and `l2grid`.
- Placeholder `L2VecBook` exists in `crates/model/src/orderbook/l2_vec.rs`.
- Runner and benchmark support for `--book l2vec` already exist.

Your job:

- replace the placeholder `L2VecBook` with a real Vec-based implementation
- preserve the existing `L2BookOps` interface
- keep all changes Rust-only
- integrate cleanly with the existing runner and benchmark harness

Primary owned file:

- `crates/model/src/orderbook/l2_vec.rs`

Allowed small shared changes only if strictly necessary:

- `crates/model/src/orderbook/mod.rs`
- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`

Do not make broad changes to:

- `crates/model/src/orderbook/l2.rs`
- workload definitions
- correctness specifications
- Python, FFI, engine, or persistence code

Implementation requirements:

- bids sorted descending by price
- asks sorted ascending by price
- one level per `(side, price)`
- `Add` and `Update` become level upsert
- `Delete` removes exact level
- `Clear` clears both sides
- metadata policy should match `L2TreeBook`

Validation requirements:

- add unit tests for insert/update/delete/clear ordering behavior
- add parity checks against baseline on synthetic sequences
- ensure small Tardis sample replay parity still passes
- run at least:
  - `cargo check -p nautilus-model --lib`
  - `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
  - any focused tests you add

Deliverable:

- working `L2VecBook`
- tests
- no regressions to shared harness
- final summary must list changed files and any remaining risks
