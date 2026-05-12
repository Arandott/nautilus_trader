# Phase 3: Targeted Optimization Pass

Date: 2026-04-09

## 目标

本阶段按 Phase 2 handoff 的顺序执行：

- 先把 canonical workload matrix 跑起来
- 再补 synthetic runner
- 再用结果决定后续优化应该往哪里投

这意味着 Phase 3 的关键交付不是“盲目先改结构”，而是先把 `grid` 的价值边界用可执行 workload 证据钉住。

## 产物

- `2026-04-09_phase3_execution_memo.md`
  - 本阶段主文档
  - 汇总 real replay、deep-query replay、dense synthetic、sparse synthetic 的结果
  - 明确写出本阶段已经可以下的结论
- `2026-04-09_phase3_phase4_handoff.md`
  - 给 Phase 4 的决策入口
  - 说明下一步是继续做 dense-oriented 优化，还是尽快收束为结论

## 代码产物

本阶段新增了 synthetic runner：

- `crates/adapters/tardis/bin/l2_synthetic_matrix.rs`
- `crates/adapters/tardis/Cargo.toml`

它服务于 Phase 2 冻结的两组 synthetic family：

- `synthetic_dense_contiguous_home_court`
- `synthetic_sparse_page_control`

## 结果目录

本阶段使用的结果目录都在：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2`

本阶段没有替换 Phase 0 冻结的 authoritative baseline。

这些结果目前的定位是：

- workload 证据
- 路线判断证据
- Phase 4/5 的输入

而不是最终 integrated authoritative compare。
