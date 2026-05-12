# Phase 1 Execution

## 代码变更

- `crates/model/src/orderbook/l2.rs`
  - 新增 `L2BookBackendKind`。
  - 补齐 `L2TreeBook` production query surface。
  - 增加 depth snapshot 和 snapshot deltas 支持。
- `crates/model/src/orderbook/book.rs`
  - 新增 `OrderBook::new_with_l2_backend`。
  - 增加 Tree backend opt-in 字段。
  - L2 Tree 更新与 generic compatibility view 同步。
- `crates/model/src/orderbook/mod.rs`
  - 导出 `L2BookBackendKind`。

## 验证

```bash
cargo test -p nautilus-model orderbook::l2::tests::test_order_book_tree_backend
```

结果: 2 passed.
