# Phase 4 Assessment: 回测撮合接入

日期: 2026-05-09

## 目标

让回测 matching engine 创建内部 `_book` 时可使用 Tree backend，并保持 L2 撮合所需查询接口可用。

## 覆盖接口

- `best_bid_price`
- `best_ask_price`
- `get_quantity_at_level`
- `get_all_crossed_levels`
- `simulate_fills`
