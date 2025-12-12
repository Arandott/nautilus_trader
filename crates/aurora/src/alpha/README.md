# Aurora AlphaEngine 模块说明

> 目标：让新同事能快速理解 `crates/aurora/src/alpha` 的控制流、默认特征、模型接口与配置项，并知道如何扩展。模块级 README 放在代码旁边便于维护；上层的概览可在 `crates/aurora/README.md` 里链接到这里。

## 代码与角色
- `engine.rs`：`AlphaEngine<M>` 主流程，持有簿、特征状态、策略、模型；公开 `handle_order_book/handle_trade`。
- `features.rs`：特征注册表，声明源 indicator、回调、取值函数；特征自行管理频率/窗口，Engine 不做节流。
- `rls.rs`：默认模型 `RlsAlpha`（RLS），`RlsParams` 参数校验与权重裁剪。
- `mod.rs`：`AlphaModel` trait 定义与 re-export。
- `python/alpha.rs`：PyO3 绑定（`AlphaEngineParams`/`AlphaEngine`/`RlsAlpha`），保持与旧 Python 行为兼容的默认值。
- 依赖：`nautilus_model`（簿/事件）、`nautilus_indicators`（`BookL1Factors`、`BookMidPriceVolEstimator` 等）。

## 事件流（handle_order_book 为例）
1. 上层传入 **已应用 deltas 的簿引用**：`handle_order_book(ts_ns, &book, inventory_qty)`（AlphaEngine 不再持有簿，也不再调用 `apply_deltas`）。
2. 特征状态更新：对每个共享 `FeatureState` 调用 `on_book`/`on_trade` 回调。
3. 预测判定：`PredictPolicy::should_predict` 根据时间/计数节流 + 可选 mid/sigma/inventory 阈值（`TriggerLogic::{Any,All}`）决定是否评估；冷启动不足 `min_updates_for_output` 时仍触发但输出 0。
4. 特征写入：`write_features` 将各 `FeatureHandle` 的值填入 `feature_buf`，调用 `model.predict`，`last_alpha_bps` 更新。
5. 入队待标注样本：`label_queue` 保存 `(ts_ns, mid, features)`，溢出时丢弃最早样本。
6. 标签出队与训练：当 `ts_now - sample.ts >= lag_ns`，用当前 mid 计算 `((mid_t - mid_0) / mid_0) * 1e4 bps`，`UpdatePolicy::should_update` 采样/裁剪/节流后调用 `model.update`。

`handle_trade` 复用了同样的预测/训练逻辑，只是默认特征没有 trade 源，更多交易特征可在注册表里扩展。

## 预测策略（PredictPolicy / PredictPolicyConfig）
- 触发条件：`time_stride_ns`（0=关闭）、`count_stride`、可选 `mid_move_bps`、`sigma_jump`、`inventory_delta`，用 `trigger_logic` 组合。
- 冷启动：`updates < min_updates_for_output` 时决策返回 `Trigger(ColdStart)`，Engine 输出 0 但仍刷新状态与队列。
- 状态：`last_trigger_ns`、`last_trigger_mid`、`snapshots_since_last` 由 Engine 维护。
- 绑定字段映射：`predict_*`、`predict_trigger_logic`、`min_updates_for_output` 来自 `AlphaEngineParams`。

## 更新策略与标签（UpdatePolicy / UpdatePolicyConfig）
- 标签定义：滞后 mid 收益，单位 bps；mid<=0 的样本直接跳过。
- 节流与过滤：`lag_ns` 到期后按 `min_update_interval_ns`（时间节流）、`count_stride`（计数节流）、`sample_rate`（LCG 抽样）决定是否训练。
- 裁剪与过滤：`label_clip_bps` 做绝对值裁剪，`label_min_abs_bps` 做弱标签过滤，`mid_required` 控制 mid<=0 是否跳过。
- 状态：`last_update_ns`、`since_last`、`rng_state`；`rng_state` 为内置 LCG，避免额外 RNG 依赖。

## 默认特征（features.rs）
- 注册表用 `register_indicator!` 绑定 indicator、回调与取值函数；同一 `source` 共享一个 indicator 状态以避免重复计算。
- 内置特征（默认 `["imbalance", "micro_skew", "sigma_rel"]`）：
  - `imbalance`：基于 `BookL1Factors`，`(bid_qty - ask_qty) / (bid_qty + ask_qty)`，无市场时输出 0。
  - `micro_skew`：`(microprice - mid) / tick_size`，tick 小于 1e-9 时会被钳制。
  - `sigma_rel`：`BookMidPriceVolEstimator::sigma_rel()`；若样本不足则回退 `base_sigma`。
- 新特征步骤：在 `features.rs` 注册（可重用 existing indicator 或自定义），声明 `name`、`source`、回调与 `value`，确保名字能被 `lookup_feature` 找到（`-` 会自动转 `_`）。需要额外 Python 配置时，在 Python 侧传入对应名称即可。

## 模型接口与默认 RLS（rls.rs）
- `AlphaModel`：`predict(&[f64]) -> bps`、`update(&[f64], label_bps)`、`dimension()`、`weights()`。
- `RlsAlpha`：小维度 RLS，`forgetting` 衰减、`ridge` 初始化对角、`a_max_bps` 限幅预测；`symmetrize` 确保矩阵非退化，参数校验严格拒绝非正/非有限值。
- 维度校验：Engine 在初始化和每次模型调用时都会检查特征长度是否与模型一致。

## Python 绑定与配置示例
```python
from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings

model = aurora_bindings.RlsAlpha(dimension=3)  # 默认 RLS 参数
params = aurora_bindings.AlphaEngineParams(
    lag_ns=300_000_000,
    tick_size=0.01,
    i_max=1.0,
    time_stride_ns=20_000_000,
    count_stride=1,
    min_updates_for_output=0,
    label_queue_len=4096,
    base_sigma=1e-6,
    features=["imbalance", "micro_skew", "sigma_rel"],
    predict_mid_move_bps=20.0,
    predict_trigger_logic="any",
    update_sample_rate=0.5,
    update_label_clip_bps=5.0,
)
engine = aurora_bindings.AlphaEngine(
    model=model,
    instrument_id=pyo3_instrument_id,  # 暂保留参数，内部忽略
    book_type=pyo3_book_type,          # 暂保留参数，内部忽略
    params=params,
)
# 事件时传入簿引用
alpha_bps = engine.handle_order_book(order_book, ts_ns, inventory_qty)
```

## 扩展与注意事项
- AlphaEngine 不再持有簿；调用方负责维护唯一簿、应用 deltas，并传入引用。
- tick_size/i_max/base_sigma 均会被钳到非负，避免无效输入导致 NaN。
- label 队列长度由 `label_queue_len` 控制；超长会丢弃最旧样本，避免 unbounded 内存。
- mid<=0 时预测直接返回上一值，更新侧在 `mid_required`=true 时跳过。
- 如需新策略字段，请保持默认值等价于旧行为，避免破坏 Python 侧兼容。
- 性能：核心路径无分配（特征向量预分配），策略/特征为内联函数；当前未接线 metrics，可在 `PredictDecision`/`UpdateDecision` 处分支计数。

## 测试与验证
- `engine.rs`：覆盖维度校验、共享状态复用、trade 触发、mid_move 阈值、标签裁剪等。
- `tests.rs`：RLS 参数校验、维度 mismatch、限幅、收敛性。
- 运行：`cargo test -p nautilus-aurora alpha::engine`

## 文档位置
- 详细设计放在本目录（贴近代码便于同步演进）。
- 上层 crate 级介绍可在 `crates/aurora/README.md` 链接到本文件，避免重复维护。
