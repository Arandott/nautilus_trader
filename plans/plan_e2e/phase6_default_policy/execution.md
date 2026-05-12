# Phase 6 Execution

## 已落地

- Rust `L2BookBackendKind::default()` 是 `Generic`。
- Rust `OrderBook::new` 始终走 `Generic`。
- Python `OrderBook` 默认参数是 `l2_backend="generic"`。
- Python `DataEngineConfig.l2_book_backend` 默认 `"generic"`。
- `BacktestVenueConfig.l2_book_backend` 默认 `"generic"`。
- `Vec` / `Grid` 在 facade 中 fallback 到 `Generic` 并记录 warning。

## 验证

默认策略由代码默认值和 model/data 编译测试覆盖。
