# Phase 6 Plan

## 执行计划

1. 保持 `OrderBook::new` 默认 generic。
2. 保持 Python `OrderBook(..., l2_backend="generic")` 默认 generic。
3. 保持 DataEngine / backtest config 默认 generic。
4. 只有显式 `tree` 时启用 Tree backend。
5. `vec` / `grid` 不作为全局默认。
