# Phase 5 Execution

## 代码变更

- `crates/data/src/engine/config.rs`
  - 新增 `l2_book_shadow_backend: Option<L2BookBackendKind>`。
- `crates/data/src/engine/mod.rs`
  - 解析 subscription params `l2_book_shadow_backend`。
  - 创建 `BookUpdater` 时传入 shadow backend。
- `crates/data/src/engine/book.rs`
  - `BookUpdater` 增加 shadow book。
  - `handle(OrderBookDeltas)` 和 `handle(OrderBookDepth10)` 后比较 primary/shadow。

## 验证

```bash
cargo test -p nautilus-data --lib
cargo test -p nautilus-data --test engine test_managed_l2
```

结果:

- `cargo test -p nautilus-data --lib`: 66 passed.
- `cargo test -p nautilus-data --test engine test_managed_l2`: 2 passed.

## 当前边界

本轮没有运行 sandbox live shadow；实盘路径按用户要求不纳入验证。已用 Rust DataEngine 离线 e2e 覆盖 shadow backend 被创建并随 deltas/depth 路径执行的场景。
