# FactorExp Live Trading Strategy 说明（2024 Phase 2）

## 概述
Phase 2 将实盘策略的信号定义与回测版本完全对齐：  
实盘直接加载 `factorexp_backtest/configs/factors.yaml`，使用相同的 `Clip(ZScore(...))` 因子表达式，并应用与回测一致的 z-score 窗口与剪裁区间。  

- **因子来源**：`FactorConfigLoader` 读取回测 YAML（默认 `../factorexp_backtest/configs/factors.yaml`）。  
- **因子选择**：通过 `factor_id`（默认 `vwap_return_std`）指定。  
- **信号输出**：FactorExp 指标返回的数值已经在 YAML 中剪裁为 `clip_min` ~ `clip_max`（默认 -2 ~ +2）。  
- **交易阈值**：为避免噪声，引入 `min_signal_magnitude`（默认 0.05），只有当因子绝对值达到阈值时才会下单。  

## 数据频率
- **默认 BarType**：`{INSTRUMENT}-15-MINUTE-LAST-INTERNAL`（已对齐 Phase 1 要求）。  
- **Warmup**：按 YAML 中 `warmup_period`（默认 5760 条）请求历史数据，确保 FactorExp 指标与回测一致地完成初始化，并通过 `request_aggregated_bars(..., update_subscriptions=True)` 预热内部聚合器。  
- **订阅**：实时仍由 `subscribe_bars(...)` 驱动，Warmup 阶段通过 `request_aggregated_bars(..., update_subscriptions=True)` 为内部聚合器灌入历史。  

## 因子定义（与回测一致）
默认因子 `vwap_return_std` 摘录（详见 YAML）：
```
Clip(
    ZScore(
        TS_Std(
            When(Greater(TS_Delta($volume, 1), 0),
                 Div(Sub(Div($amt, $volume), TS_Ref(Div($amt, $volume), 1)),
                     TS_Ref(Div($amt, $volume), 1)),
                 Div(0, 0)),
            96),
        5760),
    -2, 2)
```

- **ZScore 窗口**：5760（约 60 天的 15 分钟 Bar）。  
- **剪裁区间**：[-2, 2]。  
- **extended bar 需求**：因子依赖 `$amt`，若运行时未启用 extended bar 字段，策略会拒绝启动。  

## 信号与执行逻辑
1. 读取 FactorExp 值 `f_t`。  
2. 将 `f_t` 再次限制在 `clip_min`~`clip_max` 范围内（防御性处理）。  
3. 若 `|f_t| < min_signal_magnitude` → 不交易。  
4. 否则：  
   - `f_t > 0` → 生成 LONG 信号。  
   - `f_t < 0` → 生成 SHORT 信号。  
5. 信号改变方向时，先平仓再换向。  
6. 仓位 sizing、止损、追踪止损与 Phase 1 前保持一致（`FixedRiskSizer` + 1.5% 停损）。  

## 风险管理摘要
- **资本约束**：显式 `capital_allocation_usd`（默认继承 `max_absolute_exposure`，并受 `max_account_usage_pct` 校验）。  
- **单笔风险**：`position_risk_pct`（默认 2%）交给 `FixedRiskSizer` 计算仓位。  
- **止损**：1.5% 固定百分比 + 追踪止损。  
- **日度限制**：`max_daily_trades`, `max_daily_loss_usd`, `max_drawdown_pct`。  
- **小账户模式**：`create_small_account_config` 自动降低资本占用和信号阈值。  
- ⚠️ 当前实时策略尚未消费 `position_risk_pct` / `take_profit_pct` / `use_market_orders` / `max_daily_trades` / `max_daily_loss_usd` / `max_drawdown_pct`，仅做占位配置。  

## 日志 / 监控
- `show_portfolio_info` 输出因子最新值与阈值。  
- `get_strategy_summary()` 返回因子状态（值、clip、阈值、是否初始化完成）。  
- 关键错误（缺少因子/配置、extended bar 不可用、warmup 请求失败）会直接停止策略。  

## 环境变量（可选）
| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FACTOREXP_CONFIG_PATH` | 因子 YAML 路径 | `../factorexp_backtest/configs/factors.yaml` |
| `FACTOREXP_FACTOR_ID` | 因子 ID | `vwap_return_std` |
| `FACTOREXP_ZSCORE_PERIOD` | Z-Score 窗口 | `5760` |
| `FACTOREXP_CLIP_MIN` / `FACTOREXP_CLIP_MAX` | 剪裁区间 | `-2.0` / `2.0` |
| `FACTOREXP_MIN_SIGNAL` | 触发最小信号强度 | `0.05` |
| `FACTOREXP_CAPITAL_ALLOCATION_USD` | 显式资本预算（覆盖配置默认值） | _未设置_ |

## 下一步 (Phase 3 提前说明)
- 多头/空头仓位将扩展为 96 个 SegmentState，匹配回测架构。  
- （已完成）数据频率切换至 15 分钟内部 Bar，并使用 `request_aggregated_bars(..., update_subscriptions=True)` 预热。  
