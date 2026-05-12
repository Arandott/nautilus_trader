# Phase 0 Assessment: 行为冻结

日期: 2026-05-09

## 目标

冻结现有 `OrderBook(BookType::L2_MBP)` 的外部行为，作为 `L2TreeBook` 接入完整路径时的 oracle。

## 当前基线

- Generic L2 book 仍由 `OrderBook::new(instrument_id, BookType::L2_MBP)` 创建。
- 外部行为包含:
  - `apply_delta` / `apply_deltas`
  - `apply_depth`
  - `best_bid_price` / `best_ask_price` / size
  - `bids` / `asks`
  - `to_deltas`
  - `simulate_fills`
  - `get_quantity_at_level`
  - `get_all_crossed_levels`

## 风险判断

- `bids()` / `asks()` 返回 `&BookLevel`，这是当前 Rust API 里最难无缝替换的借用边界。
- L2 specialized backend 如果立刻替换全部 storage，会牵动 FFI、pyo3 wrapper、display、grouping 和 adapter 代码。
- 因此本轮先冻结行为，并用 generic ladder 作为兼容视图对照。
