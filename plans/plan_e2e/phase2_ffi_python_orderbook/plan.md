# Phase 2 Plan

## 执行计划

1. 新增 Rust FFI:
   - `orderbook_new_with_l2_backend`
   - `orderbook_l2_backend`
2. 更新 Cython 声明:
   - `nautilus_trader/core/rust/model.pxd`
   - `nautilus_trader/core/includes/model.h`
3. Python `OrderBook` 增加 `l2_backend="generic"`。
4. 非 `L2_MBP` 传入非 generic backend 时抛错。
5. pickle state 保存 backend 字段，并兼容旧 state。
