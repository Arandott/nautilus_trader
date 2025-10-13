# FactorExp Backtest - 多工具×多因子批量回测系统

基于 NautilusTrader 的高性能因子回测框架，支持多工具×多因子组合的批量回测。

## 📋 目录

- [功能特性](#功能特性)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [配置文件](#配置文件)
- [数据准备](#数据准备)
- [结果分析](#结果分析)
- [开发指南](#开发指南)

---

## 功能特性

### Phase C 核心功能

- ✅ **多工具×多因子批量回测**：支持任意工具和因子的组合回测
- ✅ **数据源灵活切换**：Parquet Catalog（首选）和 Feather（降级）自动切换
- ✅ **Extended Bar 支持**：支持 amt（成交额）等扩展字段
- ✅ **并行执行框架**：预留多进程并行执行能力
- ✅ **结果持久化**：JSON 格式保存回测结果，便于后续分析
- ✅ **配置驱动**：YAML 配置文件定义所有回测参数

### 支持的因子类型

- **动量因子**：价格动量、成交量动量、AMT 动量
- **流动性因子**：AMT 流向、相对强度
- **均值回归因子**：价格偏离度
- **波动率因子**：价格区间因子
- **微观结构因子**：订单流不平衡（需要 extended_bar）

---

## 架构设计

### 目录结构

```
factorexp_backtest/
├── README.md                 # 本文档
├── run_backtest.py          # Phase C 批量回测主程序
├── configs/
│   ├── __init__.py
│   ├── config_loader.py     # 配置加载器
│   └── factors.yaml         # 因子和工具配置
├── strategies/
│   ├── __init__.py
│   └── single_factor_strategy.py  # 单因子策略
├── loaders/
│   ├── __init__.py
│   ├── feather_loader.py    # Feather 数据加载器
│   └── catalog_factory.py   # Catalog 工厂
├── tools/
│   └── convert_feather_to_catalog.py  # Phase B 数据转换工具
├── data/                     # Feather 数据（降级）
├── catalog/                  # Parquet Catalog（首选）
├── results/                  # 回测结果输出
└── tests/                    # 测试文件
```

### 数据流

```
factors.yaml (配置)
       ↓
BacktestConfigLoader (解析)
       ↓
RunConfig (工具×因子组合)
       ↓
setup_backtest_engine (动态创建引擎)
       ↓
run_single_backtest (执行回测)
       ↓
Results (JSON 输出)
```

---

## 快速开始

### 1. 环境准备

```bash
# 安装 Nautilus Trader（debug 模式，编译更快）
make install-debug

# 或者 release 模式（性能更好）
make build && make install
```

### 2. 数据准备

**选项 A：使用 Parquet Catalog（推荐）**

```bash
# 从 Feather 转换到 Catalog
python tools/convert_feather_to_catalog.py \
    --feather-dir data/Binance_k_15min \
    --catalog-dir catalog \
    --instrument-id BTCUSDT \
    --venue BINANCE

# 验证 Catalog
python -c "from loaders import create_catalog; catalog = create_catalog('catalog'); print(catalog.bars())"
```

**选项 B：使用 Feather 文件（降级）**

确保 Feather 文件位于 `data/` 目录，包含以下字段：
- 标准字段：`open`, `high`, `low`, `close`, `volume`, `ts_event`
- 扩展字段（可选）：`amt`, `vwap`, `bid_volume`, `ask_volume`

### 3. 配置回测

编辑 `configs/factors.yaml`：

```yaml
# 定义工具
instruments:
  BTCUSDT:
    venue: BINANCE
    bar_spec: 15-MINUTE-LAST-EXTERNAL
    base_currency: BTC
    quote_currency: USDT
    data_source: catalog  # 或 feather

# 定义因子
factors:
  amt_momentum:
    name: "AMT Momentum"
    expression: "Clip(ZScore($amt / TS_Mean($amt, 96), 5760), -2, 2)"
    description: "Turnover amount momentum"
    requires_extended: false

# 定义 runs（工具×因子组合）
runs:
  btc_amt_momentum:
    instrument: BTCUSDT
    factor: amt_momentum
    enabled: true
    position_scale: 1.0
```

### 4. 执行回测

```bash
# 列出所有可用的 runs
python run_backtest.py --list-runs

# 执行单个 run
python run_backtest.py --run-id btc_amt_momentum

# 执行多个 runs
python run_backtest.py --run-ids btc_amt_momentum,eth_amt_momentum

# 执行所有启用的 runs
python run_backtest.py --all-runs

# 指定时间范围
python run_backtest.py --run-id btc_amt_momentum \
    --start-date 2024-01-01 \
    --end-date 2024-03-31

# 并行执行（未来支持）
python run_backtest.py --all-runs --max-workers 4
```

---

## 使用指南

### run_backtest.py - 批量回测主程序

#### 必需参数（四选一）

| 参数 | 说明 | 示例 |
|------|------|------|
| `--list-runs` | 列出所有可用的 runs | `--list-runs` |
| `--run-id` | 执行单个 run | `--run-id btc_amt_momentum` |
| `--run-ids` | 执行多个 runs（逗号分隔） | `--run-ids btc_amt_momentum,eth_amt_momentum` |
| `--all-runs` | 执行所有启用的 runs | `--all-runs` |

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--config-path` | Path | `configs/factors.yaml` | 配置文件路径 |
| `--data-path` | Path | `data/` | Feather 数据目录（降级） |
| `--catalog-path` | Path | `catalog/` | Parquet Catalog 目录（首选） |
| `--start-date` | str | `2024-01-01` | 回测开始日期 (YYYY-MM-DD) |
| `--end-date` | str | `2024-01-31` | 回测结束日期 (YYYY-MM-DD) |
| `--max-workers` | int | `1` | 并行工作进程数（当前仅支持 1） |
| `--output-dir` | Path | `results/` | 结果输出目录 |

#### 使用示例

**示例 1：查看可用配置**

```bash
python run_backtest.py --list-runs
```

输出：
```
================================================================================
AVAILABLE RUNS (Phase C)
================================================================================

Enabled Runs (11):
  btc_amt_momentum:
    Instrument: BTCUSDT.BINANCE
    Factor: AMT Momentum
    Position Scale: 1.0
  ...

Disabled Runs (1):
  btc_volume_imbalance:
    Instrument: BTCUSDT.BINANCE
    Factor: Volume Imbalance
    Status: DISABLED
```

**示例 2：执行单个回测**

```bash
python run_backtest.py \
    --run-id btc_amt_momentum \
    --start-date 2024-01-01 \
    --end-date 2024-01-31 \
    --output-dir results/jan2024
```

**示例 3：批量回测多个工具**

```bash
python run_backtest.py \
    --run-ids btc_amt_momentum,eth_amt_momentum,bnb_amt_momentum \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --output-dir results/2024_momentum
```

**示例 4：执行所有启用的 runs**

```bash
python run_backtest.py --all-runs --output-dir results/all_factors
```

### convert_feather_to_catalog.py - 数据转换工具

将 Feather 文件转换为 Parquet Catalog 格式（Phase B 工具）。

#### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `--feather-dir` | Path | 是 | Feather 文件目录 |
| `--catalog-dir` | Path | 是 | 输出 Catalog 目录 |
| `--instrument-id` | str | 是 | 工具 ID（如 BTCUSDT） |
| `--venue` | str | 是 | 交易所（如 BINANCE） |
| `--bar-spec` | str | 否 | Bar 规格（默认 15-MINUTE-LAST-EXTERNAL） |
| `--start-date` | str | 否 | 开始日期 (YYYY-MM-DD) |
| `--end-date` | str | 否 | 结束日期 (YYYY-MM-DD) |
| `--max-rows` | int | 否 | 最大转换行数（测试用） |

#### 使用示例

**转换 BTC 数据**

```bash
python tools/convert_feather_to_catalog.py \
    --feather-dir data/Binance_k_15min \
    --catalog-dir catalog \
    --instrument-id BTCUSDT \
    --venue BINANCE \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

**批量转换多个工具**

```bash
# BTC
python tools/convert_feather_to_catalog.py \
    --feather-dir data/Binance_k_15min \
    --catalog-dir catalog \
    --instrument-id BTCUSDT \
    --venue BINANCE

# ETH
python tools/convert_feather_to_catalog.py \
    --feather-dir data/Binance_k_15min \
    --catalog-dir catalog \
    --instrument-id ETHUSDT \
    --venue BINANCE

# BNB
python tools/convert_feather_to_catalog.py \
    --feather-dir data/Binance_k_15min \
    --catalog-dir catalog \
    --instrument-id BNBUSDT \
    --venue BINANCE
```

---

## 配置文件

### factors.yaml 结构

配置文件包含四个主要部分：

#### 1. instruments - 工具定义

```yaml
instruments:
  BTCUSDT:                    # 工具 ID
    venue: BINANCE            # 交易所
    bar_spec: 15-MINUTE-LAST-EXTERNAL  # Bar 规格
    base_currency: BTC        # 基础货币
    quote_currency: USDT      # 计价货币
    data_source: catalog      # 数据源：catalog 或 feather
```

#### 2. factors - 因子定义

```yaml
factors:
  amt_momentum:                    # 因子 ID
    name: "AMT Momentum"           # 因子名称
    expression: "Clip(ZScore($amt / TS_Mean($amt, 96), 5760), -2, 2)"  # 因子表达式
    description: "Turnover amount momentum"  # 描述
    requires_extended: false       # 是否需要 extended_bar 支持
```

**因子表达式语法**：

标准模式：`Clip(ZScore(<expression>, <period>), <min>, <max>)`

- `Clip(x, min, max)`：将值限制在 [min, max] 范围内
- `ZScore(x, period)`：计算 Z-score 标准化
- `$field`：引用 Bar 字段（如 `$close`, `$volume`, `$amt`）
- `TS_Mean(x, period)`：时间序列均值
- `TS_Std(x, period)`：时间序列标准差
- `Ref(x, offset)`：引用历史值

#### 3. runs - 回测任务定义

```yaml
runs:
  btc_amt_momentum:              # Run ID（工具×因子组合）
    instrument: BTCUSDT          # 引用 instruments 中的工具
    factor: amt_momentum         # 引用 factors 中的因子
    enabled: true                # 是否启用
    position_scale: 1.0          # 仓位缩放因子
    rebalance_interval: 30       # 可选：重平衡间隔（覆盖默认值）
```

#### 4. defaults - 默认参数

```yaml
defaults:
  zscore_period: 5760           # Z-score 计算周期（60天×24小时×4个15分钟）
  clip_min: -2.0                # 最小仓位（-2x 做空）
  clip_max: 2.0                 # 最大仓位（+2x 做多）
  warmup_period: 5760           # 预热周期
  rebalance_interval: 30        # 默认重平衡间隔
```

#### 5. risk_management - 风控参数

```yaml
risk_management:
  max_position_size: 2.0        # 最大仓位（2x 杠杆）
  stop_loss: 0.05               # 止损（5%）
  min_rebalance_interval: 5     # 最小重平衡间隔
  max_rebalance_interval: 480   # 最大重平衡间隔（5天）
```

#### 6. execution - 执行参数

```yaml
execution:
  slippage_bps: 10              # 滑点（10 个基点）
  commission_bps: 5             # 手续费（5 个基点）
  min_order_size: 0.001         # 最小订单量
  max_order_size: 100.0         # 最大订单量
```

### 完整配置示例

参考 `configs/factors.yaml` 文件，包含：
- 3 个 instruments（BTC, ETH, BNB）
- 8 个 factors（各类型因子）
- 11 个 enabled runs
- 完整的风控和执行配置

---

## 数据准备

### 数据源优先级

1. **Parquet Catalog**（首选）：
   - 高性能读取
   - 支持 Extended Bar
   - 列式存储，查询高效

2. **Feather 文件**（降级）：
   - 向后兼容
   - 简单易用
   - 适合小规模数据

### 数据字段要求

**必需字段**：
- `open`, `high`, `low`, `close`, `volume`
- `ts_event`（纳秒时间戳）

**扩展字段**（可选，需要 extended_bar 支持）：
- `amt`（成交额）：价格 × 成交量
- `vwap`（成交量加权平均价）
- `bid_volume`（买方成交量）
- `ask_volume`（卖方成交量）

### Extended Bar 支持检测

```python
from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS

if EXTENDED_BAR_FIELD_SPECS:
    print("✅ Extended bar support available")
    print(f"Fields: {[spec['name'] for spec in EXTENDED_BAR_FIELD_SPECS]}")
else:
    print("⚠️  Extended bar support not available - using standard OHLCV only")
```

---

## 结果分析

### 输出文件结构

```
results/
├── btc_amt_momentum_result.json    # 单个 run 结果
├── eth_amt_momentum_result.json
├── ...
└── batch_summary.json              # 批量执行汇总
```

### 结果 JSON 格式

**单个 run 结果** (`<run_id>_result.json`)：

```json
{
  "run_id": "btc_amt_momentum",
  "status": "success",
  "instrument": "BTCUSDT",
  "venue": "BINANCE",
  "factor": "AMT Momentum",
  "factor_id": "amt_momentum",
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "initial_balance": 10000.0,
  "final_balance": 10523.45,
  "total_return_pct": 5.23,
  "annualized_return_pct": 64.32,
  "total_positions": 15,
  "win_rate": 60.0,
  "avg_win": 125.50,
  "avg_loss": -78.30,
  "total_orders": 30,
  "fill_rate": 100.0
}
```

**批量执行汇总** (`batch_summary.json`)：

```json
{
  "total_runs": 11,
  "successful": 11,
  "failed": 0,
  "results": [
    { /* 单个 run 结果 */ },
    ...
  ]
}
```

### 性能指标说明

| 指标 | 说明 | 计算方式 |
|------|------|----------|
| `total_return_pct` | 总收益率 | `(final - initial) / initial * 100` |
| `annualized_return_pct` | 年化收益率 | `total_return * 365 / days` |
| `win_rate` | 胜率 | `winning_positions / total_positions * 100` |
| `avg_win` | 平均盈利 | `sum(winning_pnl) / winning_count` |
| `avg_loss` | 平均亏损 | `sum(losing_pnl) / losing_count` |
| `fill_rate` | 成交率 | `filled_orders / total_orders * 100` |

### 结果可视化（建议）

使用 Python 分析结果：

```python
import json
import pandas as pd

# 加载批量结果
with open('results/batch_summary.json') as f:
    summary = json.load(f)

# 转换为 DataFrame
df = pd.DataFrame(summary['results'])

# 按收益率排序
top_performers = df.sort_values('total_return_pct', ascending=False).head(10)
print(top_performers[['run_id', 'total_return_pct', 'win_rate', 'annualized_return_pct']])

# 计算统计指标
print(f"平均收益率: {df['total_return_pct'].mean():.2f}%")
print(f"最佳表现: {df['total_return_pct'].max():.2f}%")
print(f"最差表现: {df['total_return_pct'].min():.2f}%")
```

---

## 开发指南

### 添加新因子

1. 在 `configs/factors.yaml` 中定义因子：

```yaml
factors:
  my_new_factor:
    name: "My New Factor"
    expression: "Clip(ZScore(<your_expression>, 5760), -2, 2)"
    description: "描述你的因子逻辑"
    requires_extended: false  # 如果需要扩展字段，设为 true
```

2. 在 `runs` 中创建组合：

```yaml
runs:
  btc_my_new_factor:
    instrument: BTCUSDT
    factor: my_new_factor
    enabled: true
    position_scale: 1.0
```

3. 执行回测：

```bash
python run_backtest.py --run-id btc_my_new_factor
```

### 添加新工具

1. 准备数据（Feather 或 Catalog）
2. 在 `configs/factors.yaml` 中定义工具：

```yaml
instruments:
  SOLUSDT:
    venue: BINANCE
    bar_spec: 15-MINUTE-LAST-EXTERNAL
    base_currency: SOL
    quote_currency: USDT
    data_source: catalog
```

3. 创建工具×因子组合：

```yaml
runs:
  sol_amt_momentum:
    instrument: SOLUSDT
    factor: amt_momentum
    enabled: true
```

### 扩展策略

当前使用 `SingleFactorStrategy`，支持单因子交易。如需多因子组合策略：

1. 在 `strategies/` 创建新策略类
2. 继承 `nautilus_trader.trading.strategy.Strategy`
3. 实现 `on_start()`, `on_bar()`, `on_stop()` 方法
4. 在 `run_backtest.py` 中集成新策略

### 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_backtest_config_loader.py

# 测试数据转换
pytest tests/test_feather_to_catalog_integration.py
```

---

## 常见问题

### Q1: 如何启用并行执行？

A: 当前版本预留了并行执行框架，但尚未完全实现。未来版本将支持：

```bash
python run_backtest.py --all-runs --max-workers 4
```

### Q2: 如何使用 Extended Bar 字段？

A: 确保：
1. Rust 编译时启用 `extended_bar` feature
2. 数据包含扩展字段（如 `amt`）
3. 因子配置中设置 `requires_extended: true`

### Q3: Catalog 和 Feather 如何切换？

A: 系统自动切换：
1. 优先尝试加载 Catalog（如果 `--catalog-path` 存在）
2. 失败时自动降级到 Feather（如果 `--data-path` 存在）
3. 两者都失败则报错

### Q4: 如何调整仓位规模？

A: 在 run 配置中设置 `position_scale`：

```yaml
runs:
  btc_amt_momentum:
    instrument: BTCUSDT
    factor: amt_momentum
    position_scale: 0.5  # 减半仓位
```

### Q5: 如何添加自定义时间序列函数？

A: 需要在 Rust 侧 `nautilus_trader/indicators/factorexp/` 扩展：
1. 添加新的时间序列运算符
2. 在 Python 绑定中暴露
3. 在因子表达式中使用

---

## 许可证

本项目遵循 NautilusTrader 许可证。

---

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

- 项目主页: [NautilusTrader](https://github.com/nautechsystems/nautilus_trader)
- 文档: [官方文档](https://nautilustrader.io)
