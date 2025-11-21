Aurora Lattice v3 – 模块与代码对照
===================================

本文聚焦“代码怎么落地”与“参数/接口在哪”，内容覆盖 Grid/EV、Alpha、Fill、Regime、PositionRisk+Taker、运行路径。当前代码支持 v0.1/v0.2 prototype：Grid/Regime/TTL/安全阀已上线；Fill 仍为 heuristic，AuroraFillNet 待接入；δ_entry/q_MM/C_exit/J 以占位参数处理。

总体结构
--------
- Rust crate：`crates/aurora`
  - `alpha.rs`：RLS Alpha（trait `AlphaModel`，实现 `RlsAlpha`）。
  - `fill.rs`：触价+排队概率（heuristic）。
  - `grid.rs`：Δ/中心/数量/EV 计算。
  - `risk.rs`：波动冲击 + 软库存 hedging。
  - PyO3 绑定：`crates/aurora/src/python/{alpha,fill,grid,risk}.rs`.
- Python 策略：`Aurora_Lattice/aurora_hdg`
  - 入口策略 `strategy.py`（直接使用 `BookL1Factors`）。
  - 绑定薄层：`fill.py`、`inventory.py`、`risk.py`、`regime.py`、`position_risk.py`。
  - 配置：`config.py` + `configs/*.yaml`。
- 文档：`reports/Aurora_Lattice/prototype_guide.md`（快速跑）、本文件（模块详解）。

Alpha 模块
----------
- 代码：`crates/aurora/src/alpha.rs`
  - Trait `AlphaModel { predict(&[f64]) -> f64; update(&[f64], y_bps) }`
  - 实现 `RlsAlpha`（参数 `RlsParams { forgetting, ridge, a_max_bps }`），维度可配置。
- 绑定：`crates/aurora/src/python/alpha.rs` 暴露 `RlsParams`, `RlsAlpha`。
- Python：直接使用绑定（无自定义包装），`aurora_hdg/strategy.py` 调用 `aurora_bindings.RlsAlpha`。
- 特征与标签：特征 `(imbalance, micro_skew, sigma_rel, inventory_ratio)`；标签窗口 `alpha.tau_ms`，滞后队列 `_drain_alpha_queue`。

Fill 模块
---------
- 代码：`crates/aurora/src/fill.rs`
  - 仍是 heuristic：`p_touch`(GBM/经验触价) × `p_queue`(泊松排队耗尽)。
  - 参数：`min_p`, `use_empirical_touch`, `empirical_threshold`(1.5 tick)。
- 绑定：`crates/aurora/src/python/fill.rs` 暴露 `AuroraFillModel`, `AuroraQueueStats`。
- Python：`aurora_hdg/fill.py` 直接绑定；`strategy.py` 使用 `_queue_stats` EMA 更新 λ_MO/λ_cxl/触价率。
- TODO：接入 AuroraFillNet（ONNX 推理 + batch 接口 + TTL 输入），替换 heuristic。

Grid / EV / Inventory
---------------------
- 代码：`crates/aurora/src/grid.rs`
  - Δ：`k_sigma * sigma_px * sqrt(tau_fill) + k_s*tick + k_f*fee_buffer`，round_to_tick。
  - 中心：`s = -beta_i*(I−I*)/I_max + theta_i*alpha_bps/1e4`，`center = micro + s*Δ`。
  - I*：`clip(kappa_alpha*alpha_bps / (gamma * sigma_px^2 * tau_alpha), ±I_max)`。
  - 数量：`q_i = q0 * eta^(i-1) * (1 ∓ theta_i*(I−I*)/I_max)`，clip 到 `[q_min, q_max]`。
  - EV 占位：`edge = distance - fee_buffer - pickoff - delta_entry_ticks*tick`; `exit_penalty = (1-q_mm)*exit_cost_bps`; `unfilled_penalty = (1-p_fill)*unfilled_penalty_ticks*tick`; 方差罚 `(1-p_fill)*gamma*|I|*sigma_px*sqrt(tau_fill)`.
  - 截断：当前保留全部正 EV 档位，首个负 EV 之后未强制截断（可按需求调整）。
- 绑定：`crates/aurora/src/python/grid.rs`。
- Python：`aurora_hdg/inventory.py` 构造 planner；策略 `_grid_planner.plan` 传入 `tau_alpha_s` 与 `tau_fill_s`。
- 配置：`grid.*` + 占位参数 `exit_cost_bps, q_mm, unfilled_penalty_ticks`。

Regime 状态机
-------------
- 代码：`aurora_hdg/regime.py`
  - Regime: NORMAL / TREND_UP / TREND_DOWN / CHAOS，带 hysteresis（`hysteresis_ms`）。
  - 判定：|α| 过 `alpha_gate_bps` 且 (δ₁/x₁ >= trend_delta_ratio_threshold 或 MO 失衡 >= 阈值) → TREND；σ_rel/base_sigma >= chaos_sigma_mult → CHAOS。
  - 动作：TREND 放大 Δ、减档、裁剪档位（只留顺势侧/远侧止盈）；CHAOS 清空。
  - 可通过 `regime.mode = normal_only` 关闭。

Position Risk + Taker 安全阀
----------------------------
- 代码：`aurora_hdg/position_risk.py`
  - 跟踪 `t_since_flat`（偏离 I* 时间，阈值 `t_since_flat_threshold_I_ratio * I_max` 归零）。
  - Regime 对应 `H_max_*`；超时触发 taker 安全阀，目标是回到 I*。
  - Taker 限制：`taker_clip_qty`, `taker_max_slippage_bps`（构造保护价 IOC），`cooldown_ms`；预算 bps 暂为占位，需接成交成本扣减。

风险/波动护栏
-------------
- 代码：`crates/aurora/src/risk.rs` + `aurora_hdg/risk.py`
  - σ 突增 → WIDEN/PAUSE；软库存超限触发最小 hedge_qty（仍可与 PositionRisk 并用）。

策略主循环（`aurora_hdg/strategy.py`）
--------------------------------------
1) 更新 vol/alpha/features；α/标签按 `alpha.tau_ms` 延迟。
2) Regime 判定（alpha/δ_ratio/MO imbalance/σ 爆炸）。
3) RiskAdvisor（波动）→ widen/暂停。
4) GridPlanner：Δ/center/I*/EV -> 档位。
5) Regime 裁剪档位；PositionRisk TTL -> taker 安全阀。
6) Reanchor 节流：间隔 min(`reanchor_timeout_ms`, `ttl_ratio*tau_fill_ms`) 或中心漂移>ρΔ。

运行指引
--------
- 配置：`Aurora_Lattice/configs/default.yaml` 或 `sample_okx.yaml`；调整 instrument/tick/base_qty/i_max/venue creds。
- 启动（testnet）：`python Aurora_Lattice/run_live_trading.py --config <cfg> --env-file <env>`.
- 监控：日志中的 “Regime transition”、“Re-anchored grid…”，安全阀触发日志，实际成交/库存曲线。

下一步/待办
-----------
- 接入 AuroraFillNet（ONNX + batch predict + TTL 作为输入）。
- 用 markout/闭环统计替换 `delta_entry_ticks`, `q_mm`, `exit_cost_bps`, `unfilled_penalty_ticks`。
- 增强 taker 成本预算累加。
- 如需更重 α，可在 `alpha.rs` 实现新模型并通过 `AlphaModel` 绑定暴露。当前 RLS 已可跑。 
