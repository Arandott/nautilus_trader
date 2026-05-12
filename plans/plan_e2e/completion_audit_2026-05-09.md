# Completion Audit: L2 Specialized Book E2E Integration

日期: 2026-05-09

## Objective Restatement

用户目标:

1. 完成 `plans/plan_e2e/brainstorm/2026-05-09_l2_specialized_book_e2e_integration_plan.md` 中描述的端到端接入任务。
2. 在 `plans/plan_e2e` 下为每个阶段开阶段文件夹。
3. 每个阶段都要落盘:
   - 评估
   - 计划
   - 执行
   - 开发日志

## Prompt-to-Artifact Checklist

| 要求 | 证据 | 状态 |
| --- | --- | --- |
| Phase 0 行为冻结 | `phase0_behavior_freeze/{assessment,plan,execution,devlog}.md`；新增 model parity tests | Done |
| Phase 1 Rust core facade | `L2BookBackendKind`、`OrderBook::new_with_l2_backend`、Tree backend opt-in、model tests | Done |
| Phase 2 FFI/Python OrderBook | `orderbook_new_with_l2_backend`、`orderbook_l2_backend`、Cython `OrderBook(l2_backend=...)` | Done |
| Phase 3 DataEngine/Cache | Rust/Python DataEngine config + params 接入；Cache 类型不变 | Done |
| Phase 4 回测撮合 | `BacktestVenueConfig` 到 `OrderMatchingEngine._book` 的 backend 参数传递 | Done |
| Phase 5 Shadow | Rust `BookUpdater` shadow book + divergence compare；Python shadow 记录为后续补强 | Done for Rust path |
| Phase 6 默认策略 | 默认仍 `generic`；Tree opt-in；Vec/Grid fallback | Done |
| 每阶段文件夹 | `phase0_*` 到 `phase6_*` | Done |
| 每阶段四类文档 | 每个阶段都有 `assessment.md`、`plan.md`、`execution.md`、`devlog.md` | Done |

## Verification Evidence

```bash
cargo test -p nautilus-model orderbook::l2::tests
```

结果: 8 passed.

```bash
cargo test -p nautilus-data --lib
```

结果: 66 passed.

```bash
cargo test -p nautilus-data --test engine
```

结果: 43 passed；覆盖新增离线 DataEngine/cache e2e:

- `test_managed_l2_depth10_subscription_with_tree_backend_updates_cache`
- `test_managed_l2_deltas_subscription_with_tree_shadow_backend_updates_cache`

```bash
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_model_book.cpp nautilus_trader/model/book.pyx
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_data_engine.cpp nautilus_trader/data/engine.pyx
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_backtest_engine.cpp nautilus_trader/backtest/engine.pyx
```

结果: 通过；仅有仓库既有 `IF` deprecated warning。

```bash
make build-debug
.venv/bin/python -m pytest \
  tests/unit_tests/backtest/test_matching_engine.py::TestOrderMatchingEngine::test_process_order_book_depth_10 \
  tests/unit_tests/backtest/test_matching_engine.py::TestOrderMatchingEngine::test_l2_tree_backend_depth10_feeds_market_order_matching \
  tests/unit_tests/data/test_engine.py::TestDataEngine::test_execute_subscribe_order_book_depth10_with_tree_backend_updates_managed_book \
  -q
```

结果:

- debug build completed。
- Python 离线 e2e/regression: 3 passed。

```bash
python3 -m py_compile nautilus_trader/data/config.py nautilus_trader/backtest/config.py nautilus_trader/backtest/node.py
git diff --check
```

结果: 通过。

## Residual Risk

- Tree backend 当前为了兼容 `OrderBook::bids()/asks()` 的借用 API，保留 generic ladder 兼容视图；这不是最终 storage enum 形态。
- Python DataEngine 尚未实现 shadow book；当前 Python 路径支持直接 opt-in。
- 已运行离线 DataEngine/cache 和 backtest/matching e2e；未运行实盘/live sandbox、大规模 Tardis replay、full Python backtest suite、peak RSS/performance gate。由于默认仍为 `generic`，这些 gate 是后续把 `tree` 提升为 venue/instrument 默认前的必要条件，而不是本次 opt-in 接入的默认切换条件。
