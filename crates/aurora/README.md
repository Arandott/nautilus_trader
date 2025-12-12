## Nautilus Aurora Support Crate

Aurora 策略的核心 Rust 组件：alpha 预测、排队统计/填模、网格规划、风控、执行 diff，以及单簿 orchestrator 原型。PyO3 绑定位于 `src/python`。

### 模块概览
- `src/alpha`：事件驱动 AlphaEngine（无簿，接受外部簿引用，特征构建 + 滞后标签 + 模型训练），默认模型 `RlsAlpha`。详见 `src/alpha/README.md`。
- `src/fill`：`QueueStats` + `FillModel`。目前在 orchestrator 中用作触价/排队概率估计，后续拟迁为 indicators crate。
- `src/grid`：网格计划器，库存/EV 计算，支持 `use_fill_model=false` 关闭填模、仅靠距离/费用。
- `src/risk`：轻量风控与 regime 偏好，输出 widen/reduce/hedge 建议。
- `src/exec`：执行 diff，比较当前活跃单与计划，输出 `{submit[], cancel[]}`，支持 TTL、reanchor、限流、全撤重挂。
- `src/orchestrator`：统一持有单一权威簿 + QueueStats，串联 alpha→risk→grid→exec，返回标准 `ExecutionActions`。

### 典型流水（orchestrator）
1) 调用方维护唯一 `OrderBook`，在 `handle_orderbook(ts, deltas, active_orders, inventory)` 内应用 deltas；空簿直接返回空动作。  
2) QueueStats 更新 L1 量/触价；AlphaEngine 用簿引用预测 `alpha_bps`。  
3) RiskAdvisor 基于 σ、库存、alpha、MO 失衡给出 widen/reduce/hedge；GridPlanner 生成网格计划，hedge 以 `OrderKind::Active` 形式加入。  
4) ExecPolicy.diff(active, plan, ts, center) 产生 submit/cancel；由上层策略执行（现阶段 Python 策略仍可选择全撤重挂）。

### 架构示意
```
            ┌──────────────┐      ┌────────────┐      ┌──────────────┐
events ---> │ OrderBook    │ ---> │ QueueStats │ ---> │ AlphaEngine  │
            └──────┬───────┘      └──────┬─────┘      └──────┬───────┘
                   │                    │                  alpha_bps
                   │ mid/σ              │ λ/touch/mo_imb   │ (无簿，接受外部簿)
                   ▼                    ▼                  │
             ┌───────────┐        ┌─────────┐              │
             │ RiskAdvisor│ ----> │ GridPlan │ <-----------┘
             └─────┬─────┘        └────┬────┘
                   │ regime/widen       │ levels/center/delta
                   ▼                    ▼
                 ┌────────────────────────┐
                 │ ExecPolicy (diff)      │
                 │ active_orders + plan   │
                 └──────────┬─────────────┘
                            ▼
                ExecutionActions{submit,cancel}
```

### Python 入口（常用）
- `alpha.rs`：`RlsAlpha`、`AlphaEngineParams`、`AlphaEngine`（`handle_order_book(book, ts_ns, inventory)`）。
- `grid.rs`：`AuroraGridPlanner`（支持 `use_fill_model=False`）。
- `exec.rs`：`ExecPolicyConfig/ExecPolicy`（输入活跃单视图与计划）。
- `risk.rs`：`AuroraRiskAdvisor` + Regime 配置。
- `orchestrator.rs`：`OrchestratorConfig/AuroraOrchestrator`，组合上述组件。

### 设计要点
- **单簿**：alpha/grid 等均依赖外部簿引用，避免多处簿状态与重复特征计算。
- **可拔插**：填模可关、执行策略可切全撤/增量、QueueStats 预留独立化。
- **性能**：热路径预分配、有限克隆；配置钳制非负，避免 NaN。

### 测试
核心：`cargo test -p nautilus-aurora --lib`。  
含绑定：`cargo test -p nautilus-aurora --lib --features python`。
