# Phase 3 Agent Prompt

You are implementing `Phase 3: L2GridBook` in the NautilusTrader workspace.

Read these files first:

- `plans/cufe_undergradution/implementation/shared/2026-03-24_parallel_development_contract.md`
- `plans/cufe_undergradution/implementation/phase3/2026-03-24_phase3_l2gridbook_plan.md`

Current context:

- `Phase 0` baseline and `Phase 1` `L2TreeBook` are complete.
- The shared boundary is already wired for `baseline`, `l2tree`, `l2vec`, and `l2grid`.
- Placeholder `L2GridBook` exists in `crates/model/src/orderbook/l2_grid.rs`.
- Runner and benchmark support for `--book l2grid` already exist.

Your job:

- replace the placeholder `L2GridBook` with a real grid/tick-indexed implementation
- preserve the existing `L2BookOps` interface
- keep all changes Rust-only
- integrate cleanly with the existing runner and benchmark harness

Primary owned file:

- `crates/model/src/orderbook/l2_grid.rs`

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

- define deterministic price-to-tick conversion
- maintain one level per `(side, price)`
- keep best bid / ask lookup valid after inserts and deletes
- `Add` and `Update` become level upsert
- `Delete` removes exact level
- `Clear` clears both sides
- metadata policy should match `L2TreeBook`

Validation requirements:

- add unit tests for tick conversion and best-pointer maintenance
- add parity checks against baseline on synthetic sequences
- ensure small Tardis sample replay parity still passes
- run at least:
  - `cargo check -p nautilus-model --lib`
  - `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
  - any focused tests you add

Deliverable:

- working `L2GridBook`
- tests
- no regressions to shared harness
- final summary must list changed files and any remaining risks
