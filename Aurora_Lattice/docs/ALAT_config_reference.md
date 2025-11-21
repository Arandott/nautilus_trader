Aurora Lattice 配置全表（当前代码版）
====================================

本文覆盖 `Aurora_Lattice/configs/*.yaml` 中的 **所有** 配置项，含策略、风险、regime、position risk、taker、安全阀，以及 runtime/venue 运行参数。注：FillNet 尚未接入，EV 的部分项为占位符。

策略配置（`strategy` 节）
-------------------------
- `strategy_id`: 策略标识（字符串，默认 AURORA-HDG）。
- `order_id_tag`: 下单标签前缀。
- `instrument_id`: 交易标的，如 `KASUSDT-PERP.BINANCE`。
- `tick_size`: 最小跳动。
- `base_symbol`: 标的基币符号。

Grid（`grid`）
--------------
- `levels`: 每侧最大档数 L。
- `k_sigma`: 波动分量系数，用于 Δ。
- `k_s`: 最小 tick buffer 系数。
- `k_f`: 费用 buffer 权重。
- `fee_buffer_bps`: 手续费 buffer（bps）。
- `delta_entry_ticks`: 逆向选择常数罚分（tick），占位 δ_entry。
- `exit_cost_bps`: `(1-q_MM)*C_exit` 占位的成本上限（bps）。
- `q_mm`: 预期被动闭环概率占位 [0,1]。
- `unfilled_penalty_ticks`: 未成交占用成本 J（tick）。
- `reanchor_rho`: 中心重定位阈值（Δ 倍数）。
- `reanchor_timeout_ms`: 重定锚最小间隔（ms）。

Inventory（`inventory`）
-----------------------
- `i_max`: 仓位硬上限。
- `i_soft`: 仓位软上限（RiskAdvisor 用）。
- `gamma`: 风险厌恶系数。
- `kappa_alpha`: I* 对 α 的敏感度。
- `beta_i`: 中心库存纠偏权重 κ_I。
- `theta_i`: 中心 α 敏感度 κ_α 与数量库存 skew 权重。
- `base_qty`: 第一档基础下单量 q0。
- `eta`: 档位数量指数衰减系数。
- `q_min`, `q_max`: 单档最小/最大下单量。

Alpha（`alpha`）
---------------
- `tau_ms`: α 标签窗口（ms）。
- `a_max_bps`: 预测截断（bps）。
- `a_gate_bps`: Regime 判定用 α 门限。
- `beta_alpha`: 占位，预留用于 alpha 平滑/组合权重（当前未引用）。
- `kappa_delta`: 占位，预留用于 Δ/档位动态裁剪敏感度（当前未引用）。
- `rls_forgetting`: RLS 忘记因子。

Fill 模型（`fill_model`）
------------------------
- `tau_ms`: fill/EV 窗口（ms）。
- `ttl_ratio`: 订单 TTL 相对 tau_fill 的比例。
- `lambda_window_ms`: 队列统计 EMA 窗口。
- `use_empirical_touch`: 是否用经验触价率。
- `min_p_fill`: p_fill 底线。

执行（`exec`）
-------------
- `msg_rate_budget`: 报撤预算上限（每次 plan 返回最多订单数）。
- `maker_fee_bps`: maker 费率（bps，可为负返佣）。
- `taker_fee_bps`: taker 费率（bps）。

风险护栏（`risk`）
-----------------
- `shock_mode_sigma_mult`: σ_rel/base_sigma 超阈进入 WIDEN/PAUSE。
- `hedge_cooldown_ms`: 软库存 hedge 冷却。
- `hedge_min_qty`: 软库存 hedge 的最小量。

Regime（`regime`）
-----------------
- `mode`: `full` | `normal_only`。
- `trend_delta_ratio_threshold`: δ₁/x₁ 阈值。
- `mo_imbalance_threshold`: 市价单强度失衡阈值。
- `alpha_gate_bps`: |α| 判定门限。
- `chaos_sigma_mult`: σ_rel/base_sigma 判 CHAOS 的倍数。
- `hysteresis_ms`: Regime 切换滞后。

Position Risk（`position_risk`）
-------------------------------
- `H_max_normal_ms`: NORMAL 持仓 TTL。
- `H_max_trend_ms`: TREND 持仓 TTL。
- `H_max_chaos_ms`: CHAOS 持仓 TTL。
- `t_since_flat_threshold_I_ratio`: |I−I*| 小于此比例视为“接近平仓”重置计时。

Taker 安全阀（`taker`）
----------------------
- `taker_budget_bps_per_hour`: Taker 成本预算占位（bps/h）。
- `taker_clip_qty`: 单次 IOC clip 基础量。
- `taker_max_slippage_bps`: IOC 最大滑点（bps，保护价）。
- `cooldown_ms`: Taker 冷却。

Runtime / 账户配置（`runtime` 节）
---------------------------------
- `trader_id`: 交易员 ID。
- `log_level`: 日志级别。
- `log_directory`: 日志目录。
- `catalog_path`: 数据目录。
- `trading_mode`: `testnet` | `live`（影响默认 testnet）。
- `clients`: 字典，每个 venue 账户定义：
  - `venue`: `"BINANCE"` | `"OKX"`。
  - `testnet`: 是否使用测试网（可覆盖 trading_mode）。
  - `credentials`: 环境变量名映射（如 `api_key_env`, `api_secret_env`, `api_passphrase_env`）。
  - `use_data_client` / `use_exec_client`: 是否启用行情/交易客户端。
  - `instrument_ids`: 订阅/交易的合约列表。
  - 其他 venue 特定字段：`account_type`(Binance)、`futures_leverage`、`use_position_ids`、`use_reduce_only`、`update_instruments_interval_mins`、Retry 参数等；OKX 的 `instrument_types`、`contract_types`、`margin_mode`、`use_spot_margin`。

默认/示例配置文件
----------------
- `Aurora_Lattice/configs/default.yaml`: Binance perp 示例。
- `Aurora_Lattice/configs/sample_okx.yaml`: OKX SWAP 示例。

当前占位/不完善项
----------------
- 填单：仍为 heuristic；FillNet/ONNX 未接入。
- EV 逆向选择/尾部：`delta_entry_ticks`, `exit_cost_bps`, `q_mm`, `unfilled_penalty_ticks` 为占位；需用 markout/闭环统计替换。
- taker 预算：未实际扣减成本，仅冷却+剪裁。

修改提示
--------
- 增删字段时同步更新：`aurora_hdg/config.py`、`configs/*.yaml`、相关文档（本文件与 `reports/Aurora_Lattice/prototype_guide.md`）。 
