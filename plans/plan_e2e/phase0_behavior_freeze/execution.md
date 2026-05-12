# Phase 0 Execution

## 已落地

- 新增 `OrderBook::new_with_l2_backend` 时没有改变 `OrderBook::new` 默认行为。
- 新增 Tree backend parity 测试:
  - `test_order_book_tree_backend_facade_matches_generic_production_queries`
  - `test_order_book_tree_backend_apply_depth_matches_generic`

## 验证

```bash
cargo test -p nautilus-model orderbook::l2::tests::test_order_book_tree_backend
```

结果: 2 passed.
