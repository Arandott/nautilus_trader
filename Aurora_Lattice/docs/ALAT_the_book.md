
## 一、Aurora Lattice v3 策略书（含 DL Fill）

### 0. 全局设定与范式

* 名称： **Aurora Lattice（ALAT）** ——高频动态网格做市策略。
* 交易对象：Crypto 永续/现货，Binance/OKX 等。
* INFRA 前提：
  * 延迟和排队都 **弱于顶级 HFT** ，抢不到稳定 L1 queue head；
  * 策略设计上 **默认挂在 2–3 档开外为主** ，少抢 best bid/ask。
* 核心思路：
  1. 动态网格间距 Δ(t) 跟随波动+手续费；
  2. 报价中心 c_t 随**库存 + α_pre** 偏移；
  3. 用 **深度学习 Fill 模型** 估 p_fill；
  4. 用 **entry EV** 只放行期望非负的档位；
  5. Regime 状态机识别 NORMAL/TREND/CHAOS；
  6. **持仓 TTL + q_MM + taker 安全阀** 限制单腿暴露。

> 线上 EV 只看 t→T（挂→成），持仓阶段 T→U 由 Regime + TTL + taker 管风险，不当主 α。

---

### 1. 符号、时间尺度与参数定义

#### 1.1 时间尺度

* (t)：当前时间。
* (\tau_\alpha)： **alpha 预测窗口** （ms），如 300–500ms。
  * 用于 alpha label，决定 α_pre 描的是多长的价格漂移。
* (\tau_{fill})： **fill 预测窗口 / EV 窗口** （ms），如 300ms。
  * Aurora FillNet 预测的是在 (\tau_{fill}) 内被完全成交的概率 (p^{fill})。
* `ttl_ratio`：TTL 相对 (\tau_{fill}) 的比例（0.6–0.9）。
  * 真正订单 TTL：`TTL_ms = ttl_ratio * tau_fill_ms`。
* (H_{\max}^{pos,\text{regime}})： **持仓 TTL 上限** （ms），按 Regime 分：
  * `H_max_normal_ms`
  * `H_max_trend_ms`
  * `H_max_chaos_ms`

    超过则视为被动闭环失败，应交给 taker 处理。

#### 1.2 价格与波动

* `tick`：最小价位跳动。
* (p^{bid}_1, p^{ask}_1)：L1 价；(q^{bid}_1, q^{ask}_1)：L1 量。
* 微价格：

  [

  m_t = \frac{p^{ask}_1 q^{bid}_1 + p^{bid}_1 q^{ask}_1}{q^{bid}_1 + q^{ask}_1}.

  ]
* 相对波动：

  * (\hat\sigma_{rel,t})：每 √秒的相对波动；
  * (\hat\sigma_{px,t} = m_t \hat\sigma_{rel,t})：价波动。
* `k_sigma`： **波动分量系数** （≈0.8–1.0）。

  控制 Δ 随波动变化的力度，越大→网格越宽。
* `k_s`： **最小 tick buffer 系数** （0–1）。

  在极低波动时至少保证 Δ ≥ k_s · tick。
* `k_f`： **费用 buffer 权重** （0.2–1.0）。

  决定我们为了覆盖 maker/taker fee，在 Δ 里额外加多少空间。
* `fee_buffer_bps`：用于 Δ 的 fee buffer（bps），如 2–3bps。

网格基距：

[

\Delta_t = \text{round_to_tick}\Big(

k_\sigma \hat\sigma_{px,t}\sqrt{\tau_{fill}}

* k_s \cdot \text{tick}
* k_f \cdot m_t \cdot \frac{\text{fee_buffer_bps}}{10^4}

  \Big).

  ]

#### 1.3 网格档位与 re-anchor

* `L`：每侧最大档数（通常 3–6）。
* 第 i 档距离中心：

  [

  x_i = (i-\tfrac12)\Delta_t,\quad i=1,\dots,L.

  ]
* `reanchor_rho`：**中心重定位阈值** （例如 1.0–1.5）。

  * 当新的中心价与旧中心之差 > reanchor_rho · Δ 时，重建整张网格。
* `T_re_ms`： **最小重定锚时间间隔** （ms）。

  * 防止过于频繁 re-anchor（抖动市场情况下）。

#### 1.4 仓位与库存参数

* (I_t)：当前净仓位（数量）。
* `I_max`：仓位硬上限。

  * 绝对不能超过的仓位，用于 RiskStateMachine 和 VaR 计算。
* `I_soft`：仓位软上限（例如 0.6·I_max）。

  * 超过后开始触发更激进的 taker 去库存。
* `gamma`： **风险厌恶参数** 。

  * 单位大致是价(^{-2})，决定目标仓位对 α 的敏感度：

    [

    I_t^\star \propto \frac{\alpha_t}{\gamma \sigma_{px,t}^2\tau_\alpha}

    ]

    γ 越大 → 对 α 越不敏感，仓位更保守。
* (\kappa_I)： **库存敏感度** （0.3–1.0）。

  * 仓位偏离目标时，中心偏移多少个 Δ 去修正。
* (\kappa_\alpha)： **Alpha 敏感度** （0.1–0.5）。

  * α_t=1bps 时中心偏多少 Δ。
* 目标仓位：

  [

  I^\star_t = \text{clip}\Big(

  \frac{\kappa_\alpha \alpha_t}{\gamma (\hat\sigma_{px,t}^2\tau_\alpha)},

  -I_{\max}, I_{\max}

  \Big).

  ]
* 报价中心偏移：

  [

  s_t = -\kappa_I \frac{I_t - I^\star_t}{I_{\max}} + \kappa_\alpha \alpha_t,

  \quad

  c_t = m_t + s_t \Delta_t.

  ]

参数含义：

* (s_t)：无量纲，表示中心相对 mid 偏移了多少个 Δ；
* (\kappa_I) 大 → 有仓位时中心偏得更狠（加速回中）；
* (\kappa_\alpha) 大 → α 对中心影响更强（更 CTA）。

#### 1.5 档位数量曲线参数

* `q0`：第 1 档的基础下单数量。
* `eta`：深度递减系数（0.2–0.5）。
  * 档位数量指数衰减：

    [

    q_i = q_0 e^{-\eta (i-1)}.

    ]
* `theta_I`： **库存对档位数量的影响系数** （0.5–1.0）。
  * 决定多仓时减少 bid 量、增加 ask 量的幅度。
* `q_min`, `q_max`：单档最小/最大下单量，用于 clip。

实际数量公式：

[

q^{bid/ask} *i

= \text{clip}* {[q_{min},q_{max}]}\Big[

q_0 e^{-\eta (i-1)} \cdot

\Big(1 \mp \theta_I \frac{I_t - I^\star_t}{I_{\max}}\Big)

\Big].

]

“−” 对应买（多仓时减少买）、

“+” 对应卖（多仓时增加卖）。

#### 1.6 Alpha 模型参数

* `alpha.tau_ms = τ_α`：alpha 预测窗口（ms），如 300。
* `A_max_bps`：α 截断上限（bps），如 3.0。
* `a_gate_bps`：Regime 判定的 α 阈值（比如 1.2bps）。
* `rls_forgetting`：RLS 忘记因子（0.99 左右）。

**Alpha 模块定义：**

* 任务：预测短窗口 mid return：

  [

  y_t = \frac{m_{t+\tau_\alpha} - m_t}{m_t} \cdot 10^4\ (\text{bps}),

  \quad

  \alpha_t = \mathbb{E}[y_t \mid \text{features} *t],

  \quad \alpha_t\in[-A* {max}, A_{max}].

  ]
* 特征建议：

  * OBI（前几档盘口不平衡）；
  * microprice − mid；
  * σ_rel；
  * 近窗（100–300ms）买/卖市价单强度；
  * 当前库存比 I_t/I_max。
* 模型：

  * v0：线性 RLS；
  * v1：GBDT/XGBoost；
  * 线上只用 α_pre， **不在线上 EV 里直接加 α_post** 。

Alpha 在策略中只干三件事：

1. Regime 判定的一维信号（|α|> gate）；
2. 决定目标仓位 I^*；
3. 决定中心偏移 s_t。

#### 1.7 Fill 模型相关参数（Aurora FillNet）

* `fill.tau_ms = τ_fill`：fill horizon（ms），如 300；
* `fill.impl`: `"AuroraFillNet"`（深度学习）、或 `"heuristic"`（快速 baseline）；
* `fill.calib_refresh_min`: 多久重做校准检查（如每日）。

Aurora FillNet 输入/输出与参数放在第 3 节详细讲。

#### 1.8 逆向选择、q_MM 与 exit 成本参数

* δ_entry：通过 Markout 表估出来，按 side×level×Regime×OBI×hour 分层。
* (\hat q^{MM}_i)：在 H_max 内能 MM→MM 闭环的概率（从历史路径统计）。
* `C_exit_i`：当失败需要用 taker 出时的 **保守成本上界** （价差+费率+滑点），通常可设为：

  [

  C^{exit}_i \approx f_T^{px} + \text{slippage_cap_bps} \cdot m_t/10^4.

  ]
* `J_i`：未成交机会成本；v0 可设 0 或一个小常数（比如 0.2 tick）。

#### 1.9 手续费与执行参数

* `maker_fee_bps`：maker 费率（bps）（返佣为负）。
* `taker_fee_bps`：taker 费率（bps）。
* `msg_rate_budget`：每秒报撤消息预算（策略内部限制，≤ 交易所限速×0.6）。
* `taker_budget_bps_per_hour`：每小时可接受的 taker 成本总上限（占资金的 bps）。
* `taker_clip_qty`：单次 IOC 平仓的基础数量（≥ q0）。
* `taker_max_slippage_bps`：每次 IOC 最大容忍滑点（bps）。
* `cooldown_ms`：两次 taker 操作之间的最小间隔。

#### 1.10 Regime 判定参数

* `trend_delta_ratio_threshold`: δ₁/x₁ 阈值（如 0.6）。
  * δ₁/x₁ 高 → 内档毒性强。
* `mo_imbalance_threshold`: 市价单不平衡度 ρ_MO 阈值（如 2.5）。
  * ρ_MO = 买 MO 强度 / 卖 MO 强度。
* `alpha_gate_bps`: |α| 的阈值；
* `hysteresis_ms`: Regime 切换滞后时间（如 800ms），防止抖动。

#### 1.11 Position Risk 参数

* `H_max_normal_ms`：NORMAL 持仓 TTL 上限；
* `H_max_trend_ms`：TREND 持仓 TTL 上限（更小）；
* `H_max_chaos_ms`：CHAOS 持仓 TTL 上限（更小）；
* `t_since_flat_threshold_I_ratio`：认为“接近平仓”的 I 区间（如 0.1）——

  当 |I−I^*| < 0.1 I_max 时，把 `t_since_flat` 重置。

---

### 2. EV 公式（线上只用 Entry EV）

#### 2.1 机械半差与 δ_entry

以 mid_t 为锚：

* 第 i 档买价：(b_i = c_t - x_i)，对应机械半差：

  [

  m_t - b_i = x_i - s_t \Delta_t.

  ]
* 第 i 档卖价：(a_i = c_t + x_i)，机械半差：

  [

  a_i - m_t = x_i + s_t \Delta_t.

  ]

条件在 “被 fill” 的世界：

* 买：(\delta^{bid}_i = m_t - \mathbb{E}[m_T \mid \text{fill at } b_i])。

  → 实际 entry edge 变成 ((x_i - s\Delta) - \delta^{bid}_i)。
* 卖：(\delta^{ask}_i = \mathbb{E}[m_T \mid \text{fill at } a_i] - m_t)。

#### 2.2 Entry EV（t→T）

买单（bid，第 i 档）：

[

EV^{bid}_i

= p^{fill}_i \Big[

(x_i - s_t\Delta_t)

* \delta^{bid}_i
* f_M^{px}
* (1 - \hat q^{MM}_i) C^{exit}_i

  \Big]
* (1 - p^{fill}_i) J^{bid}_i.

  ]

卖单（ask）：

[

EV^{ask}_i

= p^{fill}_i \Big[

(x_i + s_t\Delta_t)

* \delta^{ask}_i
* f_M^{px}
* (1 - \hat q^{MM}_i) C^{exit}_i

  \Big]
* (1 - p^{fill}_i) J^{ask}_i.

  ]

解释：

* 第一部分： **成单时的期望 edge** （机械半差−逆向选择−费率−预期 exit 成本）；
* 乘 (p^{fill}_i)：考虑成单频率；
* 减 (1−p_fill)·J：考虑未成单的资源占用成本。

> v0 prototype 可以先令 ((1-\hat q^{MM}_i) C^{exit}_i=0,\ J_i=0)，只用
>
> (p^{fill}(x\mp sΔ - δ - f_M)) gating。

线上规则：

* 只挂 EV>0 的档位；
* 如果随着 i 增大，EV 单调递减，到第一个 ≤0 处截断档数。

---

### 3. Fill 模块：Aurora FillNet（深度学习版）

#### 3.1 接口定义（策略侧）

```rust
struct FillQuery {
    side: Side,           // BID or ASK
    level_idx: u8,        // 网格档位 i
    price: f64,
    ttl_ms: u32,          // τ_fill 或更短
    features: FillFeatures, // LOB + 队列 + 时段特征
}

struct FillOutput {
    p_fill: f32,          // 在 ttl_ms 内完全成交概率
    // 可选：time_to_fill_bins: Vec<f32>,
}

trait FillModel {
    fn predict_batch(&self, queries: &[FillQuery]) -> Vec<FillOutput>;
}
```

策略只依赖 `p_fill`，不关心模型内部形式。

#### 3.2 数据与 label（离线）

使用“虚拟挂单 + 回放”构造样本：

1. 从历史订单流中采样一批起点 (t_0)：
   * 覆盖不同时段 / Regime。
2. 对每个 (t_0)，构造多条虚拟挂单：
   * side ∈ {BID, ASK}；
   * 价位对应到 L1 外若干 tick（覆盖 ALAT 主要档位）；
   * size 统一为基础 q0；
   * TTL = τ_fill（或多个 TTL 版本）。
3. 回放 (t_0) 之后的真实订单流：
   * 维护该价位的 queue ahead 与本单剩余；
   * 直到：
     * 在 TTL 内全部吃完 → `label=1`，time_to_fill = t_fill − t_0；
     * 超过 TTL 仍未完全填 → `label=0`（right-censored）。
4. 构造训练样本：
   * 输入：当前 LOB 特征 + 虚拟挂单特征 + 时段特征；
   * 标签：是否在 TTL 内完全成交（或填时刻所在 bin）。

#### 3.3 特征设计（FillFeatures）

按 snapshot（建议逐 50–100ms 重采样），每条样本包括：

* LOB 截面：
  * 对 L1..L_K（比如 K=10）：
    * bid_price[i], bid_vol[i]；
    * ask_price[i], ask_vol[i]；
    * 与 mid 的距离（tick）。
* 聚合特征：
  * spread（tick）；
  * 前 k 档总 bid_depth / ask_depth；
  * OBI：((\sum q^{bid} - \sum q^{ask}))/((\sum q^{bid} + \sum q^{ask}))；
  * 近窗（200–500ms）买/卖 MO 数量/体积、撤单数量（隐含 (\lambda^{MO}, \lambda^{cxl})）。
* 虚拟挂单自身：
  * side（±1 编码）；
  * level_idx 或距 mid tick 数（d_ticks）；
  * queue_ahead（价位上已有量）；
  * ttl_ms（归一化到 [0,1]）。
* 时段/环境：
  * day_fraction（0–1）；
  * session 标记（美盘/欧盘/亚盘）。

#### 3.4 模型结构（AuroraFillNet v1）

轻量、CPU 友好版：

```text
LOB (K × F) → 1D Conv over level → ReLU → Global pooling → h_lob
挂单&时段特征 → MLP → h_ord
[h_lob, h_ord] concat → 2~3层 MLP → σ(logit) → p_fill
```

* Conv1d over level 捕捉“价位结构”；
* h_ord 捕捉 queue、side、TTL 等细节；
* 输出 p_fill(TTL)。

损失：

* Binary cross-entropy；
* 评估：
  * Brier score；
  * Calibration curve（pred bin vs actual）。

> v2 可以升级到序列 + 生存分析（Conv+Transformer + hazard head），但 prototype 不必一上来搞这么重。

#### 3.5 部署与推理

* 训练在 Python（PyTorch/TF），导出 ONNX；
* Rust/C++ 侧用 ONNX Runtime 推理，实现 `FillModel` trait；
* 每次决策：
  1. build LOB snapshot features；
  2. 为所有候选网格档位构造 `FillQuery` 数组；
  3. 一次 batch 推理得到所有 `p_fill_i`；
  4. 喂给 EV 模块。

监控指标（线上看板）：

* 各档、各 Regime 的 p_fill calibration；
* EV>0 的挂单实际 realized pnl 分布；
* 推理延迟 P50/P99。

---

### 4. Regime 状态机与 Position Risk

#### 4.1 Regime 判定

* NORMAL：
  * |α_t| < alpha_gate_bps；
  * δ₁/x₁ ≤ trend_delta_ratio_threshold；
  * ρ_MO ≤ mo_imbalance_threshold。
* TREND_UP：
  * α_t > alpha_gate_bps；
  * 且 δ₁/x₁ 或 ρ_MO 达阈值之一；
  * 持续 ≥ hysteresis_ms。
* TREND_DOWN：同理 α_t<−gate，符号对称。
* CHAOS：
  * σ_rel 短期爆炸、价位跳动频繁、拒单/延迟异常达阈。

Regime 决定：

* 可挂档位的集合（TREND 下只挂顺势侧近档+逆势侧远档止盈）；
* Δ 放大倍数、L 减少、TTL 缩短；
* Position TTL（H_max）大小。

#### 4.2 Position Risk（单腿暴露）

维护：

* `t_since_flat`：从“仓位接近目标（|I−I*|<0.1I_max）”开始计时；
* 每次 |I−I*|<阈值 → reset；否则累加。

规则：

* 如果 `t_since_flat > H_max_pos(current_regime)` 且 |I−I*|>某小阈值：
  1. 停止在风险方向继续挂被动单；
  2. 触发 taker 安全阀分片还仓：
     * 每次 IOC size= min(|I−I*|, taker_clip_qty)；
     * 滑点受 taker_max_slippage_bps 限制；
     * 冷却间隔 cooldown_ms；
     * 总成本受 taker_budget_bps_per_hour 控制。

这样 **q_MM** 的定义就和 H_max_pos 对齐：

q_MM(ctx) = 在 H_max_pos 内通过被动对侧成功平仓的比例。

---

### 5. 策略主循环（逻辑顺序）

伪代码（和你 Nautilus 实现对应）：

1. **更新 LOB / 波动 / Alpha**
   * 计算 m_t, σ_px；
   * 用 AlphaModel 预测 α_t；
   * 维护 λ_MO, λ_cxl, OBI 等。
2. **判断 Regime、Position Risk**
   * detect_regime(α_t, δ₁/x₁, ρ_MO, σ_rel, feed_质量)；
   * 更新 t_since_flat，并按 Position TTL 看是否需要触发 taker。
3. **计算 Δ、中心 c_t、档位集合**
   * Δ = Δ(m_t, σ_px, fee_buffer)；
   * I^*, s_t, c_t；
   * 生成候选档价（按 Regime 限定可挂档位）。
4. **构造 FillQuery batch → AuroraFillNet**
   * 为每个候选档构造 FillQuery（side, level_idx, price, ttl_ms, features）；
   * 一次 batch 推理获得 p_fill_i。
5. **查 δ_entry、q_MM、C_exit，计算 EV**
   * 对每个(i, side)，查 δ_entry_i(ctx)、q_MM_i(ctx)、C_exit_i；
   * 算 EV^{bid/ask}_i；
   * 只保留 EV>0 的档，按 EV 排序，截断至 `msg_rate_budget` 限制。
6. **报撤与 re-anchor**
   * 若新中心与旧中心差 > reanchor_rho*Δ 或时间> T_re_ms → re-anchor grid；
   * 仅当目标价或 EV 变化足够大时撤换（节流）；
   * 提交 post-only 限价单。
7. **taker 安全阀**
   * 若 |I|>I_soft 或 VaR 超阈 或 Position TTL 超时 →

     调用 `IOC_to(I_target)` 分片还仓。

---

## 二、Prototype 教程：怎么“最快跑起来”

你现在真正想要的是： **我同事 1–2 周内能敲出一版能在仿真/小仓跑的 ALAT v0.1** ，不是一上来把所有花活都写完。

我给你一个非常具体的路线，分两层：

* v0.1： **极简可运行版本** （不需要 DL Fill，先通路）；
* v0.2： **替换 Fill 为 AuroraFillNet** ，开始认真用 p_fill。

### Step 0：前置条件

必须先有：

1. **行情与撮合适配** （这应该已经有了）：

* 能订阅 L2 order book（至少 L10），tick 数据；
* 能发 post-only 限价、IOC 市价；
* 能拿到成交回报更新 position。

1. **简单的 volatility 估计器** ：

* 如 EWMA(mid 差分) → σ_rel, σ_px。

这个是 infra 层，不展开。

---

### Step 1：实现 v0.1 极简 Aurora Lattice

 **目标** ：不依赖 alpha，不依赖 DL Fill，只用 heuristic，验证整体网格架构 + inventory + taker + risk。

#### 1.1 模块启用情况

* Alpha：关闭（α_t ≡ 0）；
* Regime：只用 NORMAL（TREND/CHAOS 逻辑先禁用）；
* Fill：`impl="heuristic"`；
  * p_fill 只按 level 用固定值（比如 L1 0.5, L2 0.3, L3 0.15）；
* δ_entry：用固定罚分（比如 1 tick）；
* q_MM, C_exit, J：都设 0，不进 EV。

#### 1.2 参数建议（v0.1 默认）

```yaml
grid:
  L: 3
  k_sigma: 0.9
  k_s: 0.5
  k_f: 0.5
  fee_buffer_bps: 3.0
  reanchor_rho: 1.2
  T_re_ms: 400

inventory:
  I_max: "<by_symbol>"       # 比如 10–30 倍 q0
  I_soft: 0.6 * I_max
  gamma: 2.0e-6
  kappa_I: 0.6
  kappa_alpha: 0.0           # v0.1 不用 alpha 偏斜
  q0: "<base_qty>"           # 让单次手续费在你能接受范围
  eta: 0.3
  theta_I: 0.8
  q_min: 0.2 * q0
  q_max: 2.0 * q0

alpha:
  mode: "off"
  tau_ms: 300
  A_max_bps: 3.0

fill_model:
  impl: "heuristic"
  p_fill_L1: 0.5
  p_fill_L2: 0.3
  p_fill_L3: 0.15

execution:
  msg_rate_budget: 20
  maker_fee_bps: 0.0
  taker_fee_bps: 2.0
  ttl_ratio: 0.7   # TTL = 0.7 * tau_fill;  tau_fill=300ms

risk:
  shock_mode_sigma_mult: 2.5
  hedge_cooldown_ms: 800
  hedge_min_qty: 2 * q0

regime:
  mode: "normal_only"
  trend_delta_ratio_threshold: 0.6   # 暂时不用
  mo_imbalance_threshold: 2.5
  alpha_gate_bps: 1.2
  hysteresis_ms: 800

position_risk:
  H_max_normal_ms: 2500
  H_max_trend_ms: 1500       # v0.1 无效
  H_max_chaos_ms: 800        # v0.1 无效
  t_since_flat_threshold_I_ratio: 0.1

taker:
  taker_budget_bps_per_hour: 8.0
  taker_clip_qty: 2 * q0
  taker_max_slippage_bps: 3.0
  cooldown_ms: 500
```

#### 1.3 v0.1 要实现的逻辑（最小集）

1. **Delta & Grid 构建** （已给公式）：

* 从 σ_px 和 fee_buffer 算 Δ；
* L=3，生成 x_i, b_i, a_i；

1. **Inventory 偏斜** ：

* I^* 用 α=0 简化（I^* ≡ 0）；
* 只用 κ_I 调整中心和档位数量；

1. **Heuristic p_fill 与 EV** ：

* 每个 level 用常数 p_fill；
* δ_entry 固定为 1 tick（深档逆向选择小一点可以更保守一些）；
* EV_i = p_fill_i * (x−δ−费用)，J=0；
* 只挂 EV>0 档位；

1. **Position Risk + taker** ：

* 实现 t_since_flat 计时；
* 当 t_since_flat > H_max_normal_ms 且 |I|> 某阈值 → 每隔 cooldown_ms 用 IOC 平一小口；
* 控制 taker 成本不超过 taker_budget_bps_per_hour；

1. **报撤节流 + re-anchor** ：

* center 漂移>reanchor_rho*Δ 或超过 T_re_ms → 重建网格；
* 不要在 mid 向你不利方向小抖动时频繁撤换。

**这一版回测/小仓 live 后，你能看到：**

* 网格在 NORMAL 区间能不能稳定吃点差（即使很粗糙）；
* 仓位会不会堆到危险位置；
* taker 是否是 tail 而不是主来源。

---

### Step 2：接入 Aurora FillNet（v0.2）

当 v0.1 engine 稳定后，启动你那套 DL Fill pipeline：

1. 离线回放构建 Fill 数据集（ghost orders + label）；
2. 训练 AuroraFillNet v1（Conv+MLP），只输出 p_fill(TTL=τ_fill)；
3. 导出 ONNX，写 Rust/C++ 侧 `FillModel::predict_batch`；
4. 在策略配置中把 `fill_model.impl` 改成 `"AuroraFillNet"`；
5. 监控：
   * p_fill 的 calibration（各档、各 Regime）；
   * EV>0 挂单的 realized pnl 分布是否显著改善；
   * 策略整体 pnl / 波动 / taker 成本变化。

---

### Step 3：逐步打开高级功能

在 v0.2 稳定后，按优先级加东西：

1. **alpha_pre 打开** ：

* 用简单 RLS / GBDT 训练 α_pre；
* 先只用在 Regime 判定和 I^*，κ_α 设小（0.1–0.2）；

1. **δ_entry 表替换掉固定 1tick** ：

* 用填单后 +50ms Markout 做 δ_entry(level, Regime, OBI) 表；
* 线上查表代替常数；

1. **Regime(TREND/CHAOS)** ：

* 用 |α|, δ₁/x₁, ρ_MO 标注历史数据，检查 TREND 区间内的 δ/x；
* 上线 TREND：关闭逆势侧内档，只挂顺势侧近档+远档止盈；

1. **q_MM & C_exit** ：

* 按 H_max 统计 MM→MM 闭环比例和 exit 成本分布；
* 在 EV 里加保守项 `(1−q_MM)*C_exit`，镀一层“尾部保险”。

---

如果你愿意，你可以把上面这一整段直接当作：

* `docs/spec_v3.md`（策略书）；
* `docs/prototype_guide.md`（落地教程）。

下一步你可以做的事有两个：

1. 把所有参数表和含义直接抄进你们的 config schema / 注释；
2. 选一个你最关心的模块先推进（比如：先把 AuroraFillNet 做出来，还是先搞 δ_entry 表），我可以帮你把那个模块拆到“表结构 / SQL / feature 列 / PyTorch skeleton”的粒度，让你同事照着写。
