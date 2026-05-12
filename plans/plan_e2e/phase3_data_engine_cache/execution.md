# Phase 3 Execution

## 代码变更

- `nautilus_trader/data/config.py`
  - 新增 `l2_book_backend: str = "generic"`。
- `nautilus_trader/data/engine.pyx`
  - `_setup_order_book` 支持 `command.params["l2_book_backend"]` 覆盖。
  - `_create_new_book` 传入 `l2_backend`。
  - snapshot replay 临时 book 也传入 backend。
- `nautilus_trader/data/engine.pxd`
  - 增加 `_l2_book_backend` 字段和 `_create_new_book` 新签名。
- `crates/data/src/engine/config.rs`
  - 新增 `l2_book_backend`。
- `crates/data/src/engine/mod.rs`
  - Rust managed book 创建时使用 backend-aware constructor。
  - 支持订阅 params `l2_book_backend`。
  - 修正 JSON string params 解析，避免 `"tree"` 被当作带引号的未知值。
- `crates/data/tests/engine.rs`
  - 新增离线 DataEngine/cache e2e，覆盖 subscription params 到 managed book cache 的链路。
- `tests/unit_tests/data/test_engine.py`
  - 新增 Python DataEngine 离线 e2e，覆盖 `SubscribeOrderBook(..., params={"l2_book_backend": "tree"})` 到 cache book BBO。

## 验证

```bash
cargo test -p nautilus-data --lib
cargo test -p nautilus-data --test engine
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_data_engine.cpp nautilus_trader/data/engine.pyx
.venv/bin/python -m pytest tests/unit_tests/data/test_engine.py::TestDataEngine::test_execute_subscribe_order_book_depth10_with_tree_backend_updates_managed_book -q
```

结果:

- Rust: 66 passed.
- Rust DataEngine engine tests: 43 passed.
- Cython: 通过，仅有既有 `IF` deprecated warning。
- Python DataEngine offline e2e: 1 passed.
