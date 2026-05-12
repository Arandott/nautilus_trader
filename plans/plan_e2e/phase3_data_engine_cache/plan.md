# Phase 3 Plan

## 执行计划

1. Python `DataEngineConfig` 增加 `l2_book_backend`。
2. Python DataEngine managed book 创建时读取 config 或 subscription params。
3. Rust `DataEngineConfig` 增加 `l2_book_backend`。
4. Rust DataEngine `setup_book_updater` 使用 backend-aware constructor。
5. Cache API 不改签名。
