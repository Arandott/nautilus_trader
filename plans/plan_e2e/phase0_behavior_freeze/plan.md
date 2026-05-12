# Phase 0 Plan

## 执行计划

1. 保留 `OrderBook::new` 的默认 generic 行为。
2. 为 Tree 后端新增 model-level parity 测试，覆盖 production API:
   - `apply_delta`
   - `apply_depth`
   - BBO
   - top N
   - `get_quantity_at_level`
   - `get_all_crossed_levels`
   - `simulate_fills`
   - `to_deltas`
3. 明确 L2 backend 不承诺 L3 per-order time priority。
4. 记录已知折中: 当前 Tree facade 为了不破坏 `bids()/asks()` 的借用 API，保留 generic ladder 兼容视图。
