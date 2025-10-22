# Live Trading Tests

实时交易系统测试套件，用于验证实盘数据流的正确性。

## ⚠️ 重要说明

这些测试**默认不会在CI中运行**，需要手动执行。原因：

1. 需要网络连接到Binance
2. 测试时间较长（60-120秒）
3. 依赖外部服务可用性

## 测试列表

### `test_live_amt_field.py`

验证实时数据流中bar对象的`amt`（成交额）字段累积是否正确。

**测试逻辑**:
1. 连接Binance Futures实时数据流
2. 订阅BTCUSDT-PERP的TradeTick流
3. 使用TickBarAggregator聚合100-tick bars
4. 验证每个bar的`amt`字段 = sum(price × size)
5. 使用`Decimal`精度计算，容差<0.01%

**前置条件**:
- Extended bar特性已启用（编译时开启）
- 网络连接（可访问Binance）
- 无需API密钥（仅使用公开数据）

## 运行方法

### 方法1: 使用testnet（推荐）

```bash
# 设置环境变量启用实时测试
export NT_ENABLE_LIVE_TESTS=1

# 运行测试（默认使用testnet）
pytest factorexp_live_trading/tests/test_live_amt_field.py -v -s

# 或直接运行单个测试
NT_ENABLE_LIVE_TESTS=1 pytest factorexp_live_trading/tests/test_live_amt_field.py::test_live_amt_accumulation_btcusdt -v -s
```

### 方法2: 使用mainnet

```bash
# 同时设置两个环境变量
export NT_ENABLE_LIVE_TESTS=1
export NT_USE_MAINNET=1

# 运行测试
pytest factorexp_live_trading/tests/test_live_amt_field.py -v -s
```

### 方法3: 直接运行Python脚本

```bash
# 使用testnet
NT_ENABLE_LIVE_TESTS=1 python factorexp_live_trading/tests/test_live_amt_field.py

# 使用mainnet
NT_ENABLE_LIVE_TESTS=1 NT_USE_MAINNET=1 python factorexp_live_trading/tests/test_live_amt_field.py
```

## 环境变量说明

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `NT_ENABLE_LIVE_TESTS` | ✅ 是 | 未设置 | 设置为`1`启用实时测试 |
| `NT_USE_MAINNET` | ❌ 否 | 未设置 | 设置为`1`连接mainnet，否则使用testnet |

## 预期输出

成功运行时会看到：

```
================================== test session starts ===================================
...
================================================================================
Real-Time Amt Field Verification Test
================================================================================
Network: TESTNET
Extended Bar: ENABLED
================================================================================

✅ Connected to Binance Futures

✅ Instrument loaded: BTCUSDT-PERP.BINANCE

Bar Configuration:
  - Type: BTCUSDT-PERP.BINANCE-100-TICK-LAST-EXTERNAL
  - Aggregation: 100 ticks

✅ Subscribed to live data stream

Collecting data for 120 seconds...
================================================================================

  📊 Trades: 10, Expected Amt: $502,345.67
  📊 Trades: 20, Expected Amt: $1,004,691.34
  ...

🎯 Bar #1 Completed:
   OHLCV: 50000.0 / 50100.0 / 49900.0 / 50050.0 / 1.523
   Trades: 100
   Actual amt:   $76,234.56
   Expected amt: $76,234.56
   Difference:   $0.00 (0.000000%)
   ✅ PASS: amt field accurate (error < 0.01%)

...

================================================================================
TEST RESULTS
================================================================================
  Network: TESTNET
  Bars collected: 2
  All amt fields accurate within 0.01%

  Bar #1:
    Actual:   $76,234.56
    Expected: $76,234.56
    Error:    0.000000%

  Bar #2:
    Actual:   $82,123.45
    Expected: $82,123.45
    Error:    0.000000%

================================================================================
✅ TEST PASSED
================================================================================

========================= 1 passed in 125.34s ============================
```

## 故障排查

### 测试被跳过

```
SKIPPED [1] test_live_amt_field.py:XX: NT_ENABLE_LIVE_TESTS environment variable not set
```

**解决**: 设置`NT_ENABLE_LIVE_TESTS=1`

### Extended bar特性未启用

```
SKIPPED [1] test_live_amt_field.py:XX: extended_bar feature is not enabled in this build
```

**解决**: 重新编译，确保`configs/extended_bar_fields.toml`存在且不为空

### 连接超时

```
TimeoutError: Connection to Binance timed out
```

**可能原因**:
1. 网络问题 - 检查防火墙/代理设置
2. Binance服务不可用 - 稍后重试
3. Testnet维护中 - 尝试使用mainnet（`NT_USE_MAINNET=1`）

### 没有收集到bar

```
AssertionError: Expected at least 1 bar, got 0
```

**可能原因**:
1. 市场交易量太低 - 尝试更活跃的时段
2. 测试时间太短 - 增加`await asyncio.sleep()`时长
3. 连接断开 - 检查网络日志

## 开发指南

### 添加新的实时测试

1. 在`factorexp_live_trading/tests/`创建新文件
2. 添加skip标记：
   ```python
   pytestmark = pytest.mark.skipif(
       not os.getenv("NT_ENABLE_LIVE_TESTS"),
       reason="..."
   )
   ```
3. 使用**TradingNode模式**（官方推荐）：
   ```python
   # 创建配置
   config = TradingNodeConfig(...)
   node = TradingNode(config=config)

   # 注册factory（必须在build之前）
   node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)

   # 构建和启动
   node.build()
   await node.kernel.start_async()

   # 使用...

   # 清理（只停止kernel，不要dispose）
   await node.kernel.stop_async()
   ```
4. 使用`Decimal`进行精确计算
5. 在cleanup阶段注销所有订阅

### 最佳实践

1. **资源清理**: 始终在`try...finally`中清理，但**不要**调用`node.dispose()`
2. **超时保护**: 使用`@pytest.mark.timeout()`防止挂死
3. **精度计算**: 金融数据使用`Decimal`而非`float`
4. **错误容差**: 设置合理的误差阈值（如0.01%）
5. **环境隔离**: 默认使用mainnet（公开数据无需API key）
6. **事件循环管理**: pytest-asyncio管理循环，测试中只调用`kernel.stop_async()`，不要`dispose()`

## 参考资料

- [Extended Bar Plan](../../plans/backtest2livetrading/extended_bar_amt_plan.md)
- [Test Plan](../../plans/backtest2livetrading/test_live_amt_field_plan.md)
- [官方示例](../../examples/live/binance/binance_spot_and_futures_market_maker.py)
