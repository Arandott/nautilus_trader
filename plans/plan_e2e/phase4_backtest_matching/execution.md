# Phase 4 Execution

## 代码变更

- `nautilus_trader/backtest/config.py`
  - `BacktestVenueConfig.l2_book_backend`。
- `nautilus_trader/backtest/node.py`
  - run config 到 engine 的参数传递。
- `nautilus_trader/backtest/engine.pyx`
  - `BacktestEngine.add_venue` 增加参数。
  - `SimulatedExchange` 保存 backend。
  - `OrderMatchingEngine` 保存 backend 并构造 backend-aware `_book`。
  - 保持 `OrderMatchingEngine` 直接构造兼容性，`l2_book_backend` 为默认可选参数。
- `nautilus_trader/backtest/engine.pxd`
  - 增加 cdef readonly 字段。
- `tests/unit_tests/backtest/test_matching_engine.py`
  - 新增离线 backtest/matching e2e，覆盖 Tree backend depth10 book 到 market order fill。

## 验证

```bash
.venv/bin/cython -3 --cplus -I . -o /tmp/nautilus_backtest_engine.cpp nautilus_trader/backtest/engine.pyx
python3 -m py_compile nautilus_trader/data/config.py nautilus_trader/backtest/config.py nautilus_trader/backtest/node.py
make build-debug
.venv/bin/python -m pytest tests/unit_tests/backtest/test_matching_engine.py::TestOrderMatchingEngine::test_l2_tree_backend_depth10_feeds_market_order_matching -q
```

结果:

- Cython: 通过，仅有既有 `IF` deprecated warning。
- Python syntax: 通过。
- debug build completed。
- Python backtest/matching offline e2e: 1 passed.
