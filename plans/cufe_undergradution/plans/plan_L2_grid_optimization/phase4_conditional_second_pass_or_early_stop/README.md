# Phase 4: Conditional Second Pass Or Early Stop

日期：2026-04-10

## 目录说明

- [2026-04-10_phase4_execution_memo.md](./2026-04-10_phase4_execution_memo.md)
  - 记录本轮结构压缩改动、Phase 3 -> Phase 4 的前后对比，以及是否满足早停条件。
- [2026-04-10_phase4_phase5_handoff.md](./2026-04-10_phase4_phase5_handoff.md)
  - 给 Phase 5 的收束建议，明确最终结论应该如何表述。

## 结果目录

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/layout`
  - Phase 4 的布局诊断输出。
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/real_shallow_control_btcusdt_10m`
  - 真实浅簿控制组的 `l2grid` 复测结果。
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/real_deep_query_sparse_replay_btcusdt_10m/depth500_q100`
  - 真实深查询稀疏 replay 的 `l2grid` 复测结果。
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/synthetic_dense_contiguous_home_court_1024lvl/depth500_q100`
  - dense synthetic 的 `l2grid` 复测结果。
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/synthetic_sparse_page_control_1024lvl/depth500_q100`
  - sparse synthetic 的 `l2grid` 复测结果。

## 代码改动

- `crates/model/src/orderbook/l2_grid.rs`
  - `GridLevel` 不再保存完整 `Price`，改为保存 `Quantity + price_precision`，价格由 `base_tick + slot` 派生。

## 本阶段结论

- 这轮压缩把 `grid_page_size_bytes` 从 `5152` 降到了 `4128`，静态 page 体积下降约 `19.9%`。
- 真实 sparse replay 上，`l2grid` 的 throughput 和 RSS 都有改善。
- 但 sparse synthetic 下的吞吐和 query 没有改善，dense synthetic 的 query 还明显变慢。
- 因此这轮结果更像是“确认了压缩方向能缓解一部分固定成本”，而不是“已经把 grid 救成默认工程方案”。
