# CUFE Undergraduate Playground

This directory is the working area for thesis-related engineering and outputs.

## Layout

- `scripts/`: experiment helpers, data loaders, and result-processing utilities
- `benchmarks/`: microbenchmarks and benchmark harnesses
- `experiments/`: experiment scripts, configs, and runners
- `results/`: raw outputs, summary tables, and processed artifacts
- `figures/`: plots and exported paper-ready images
- `notes/`: technical notes, measurement records, and short drafts
- `slides/`: LaTeX slide decks and presentation assets

## Scope

Keep planning and brainstorming documents under `plans/`.
Keep implementation work and experiment deliverables here.
Rust production changes still belong in `crates/`, not in this workspace.

## L2 order book benchmark and e2e commands

See the repository-root `README_L2_BOOK.md` for the current commands to run:

- criterion microbenchmarks for baseline/tree/vec/grid
- Tardis replay performance comparisons
- Rust parity and DataEngine/cache e2e checks
- Python DataEngine and backtest/matching e2e checks
