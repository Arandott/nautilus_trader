# Phase 4 Plan

## 执行计划

1. `BacktestVenueConfig` 增加 `l2_book_backend`。
2. `BacktestNode` 把 venue config 传入 engine。
3. `BacktestEngine.add_venue` 传入 `SimulatedExchange`。
4. `SimulatedExchange.add_instrument` 传入 `OrderMatchingEngine`。
5. `OrderMatchingEngine` 创建 `_book` 时传给 Cython `OrderBook`。
