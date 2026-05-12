# Phase 5 Plan

## 执行计划

1. Rust `DataEngineConfig` 增加 `l2_book_shadow_backend`。
2. Rust subscription params 支持 `l2_book_shadow_backend`。
3. `BookUpdater` 维护 per-instrument shadow book。
4. 每次 `OrderBookDeltas` / `OrderBookDepth10` 后比较 primary 和 shadow。
5. Divergence 用 error log 输出完整上下文。

## 后续补强

- Python DataEngine shadow。
- top50 / checksum。
- sandbox live run 记录。
