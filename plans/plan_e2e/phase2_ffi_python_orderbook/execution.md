# Phase 2 Execution

## 代码变更

- `crates/model/src/ffi/orderbook/book.rs`
  - 新增 backend-aware constructor FFI。
  - 新增 backend 查询 FFI。
- `nautilus_trader/model/book.pyx`
  - `OrderBook(..., l2_backend="tree")` 可构造 Tree backend。
  - 新增 `l2_backend` property。
  - pickle state 追加 backend 字段。
- `nautilus_trader/model/book.pxd`
  - 增加 `_l2_backend` 字段。
- `nautilus_trader/core/rust/model.pxd`
  - 增加新 FFI 声明。
- `nautilus_trader/core/includes/model.h`
  - 增加新 C header 声明。

## 验证

```bash
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_model_book.cpp nautilus_trader/model/book.pyx
```

结果: 通过。仅出现仓库既有 `IF` deprecated warning。
