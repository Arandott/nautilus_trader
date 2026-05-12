# Phase 1 Plan

## 执行计划

1. 在 `crates/model/src/orderbook/l2.rs` 增加 backend enum。
2. 在 `crates/model/src/orderbook/book.rs` 增加 backend-aware constructor。
3. 让 `Tree` backend 支持:
   - `apply_depth`
   - `to_deltas`
   - BBO
   - exact quantity
   - crossed levels
   - simulated fills
4. 通过 model-level parity 测试。
