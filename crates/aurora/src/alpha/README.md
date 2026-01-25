# Aurora AlphaEngine 模块说明

> 目标：让新同事能快速理解 `crates/aurora/src/alpha` 的控制流、默认特征、模型接口与配置项，并知道如何扩展。模块级 README 放在代码旁边便于维护；上层的概览可在 `crates/aurora/README.md` 里链接到这里。

## 代码与角色
- `engine/mod.rs`：`AlphaEngine<M>` 主流程，持有簿、特征状态、策略、模型；公开 `handle_order_book/handle_trade`。
- `engine/policies.rs`：采样与输出策略（`SamplePolicy`/`OutputPolicy`）。
- `engine/feature_runtime.rs`：特征状态更新与写入逻辑（按输入标签路由到特征子集）。
- `features.rs`：特征注册表（宏表生成 `Feature` 枚举与 `build_feature/lookup_feature`），每个特征标注 `Inputs`（BOOK/TRADE/QUOTE）；特征自行管理频率/窗口，Engine 不做节流。
- `models/rls.rs`：默认模型 `RlsAlpha`（RLS），`RlsParams` 参数校验与权重裁剪。
- `training/trainer.rs`：训练器抽象（`Trainer`/`RlsTrainer`）与 `UpdatePolicy`，集中管理更新节流/采样/裁剪。
- `training/labeler.rs`：延迟标签 `Labeler` 与 `Sample/LabeledSample` 定义。
- `models/model_handle.rs`：Predictor/ModelHandle 抽象与 `ArcSwapModelHandle`，支持离线模型热切换。
- `models/model_registry.rs`：版本化模型注册表（内存实现），管理版本/元数据并驱动热切换。
- `models/onnx.rs`：ONNX Predictor 骨架（由外部 runtime 提供 session 实现）。
- `mod.rs`：`AlphaModel` trait 定义与 re-export。
- `python/alpha.rs`：PyO3 绑定（`AlphaEngineParams`/`AlphaEngine`/`RlsAlpha`），保持与旧 Python 行为兼容的默认值。
- 依赖：`nautilus_model`（簿/事件）、`nautilus_indicators`（`BookL1Factors`、`BookMidPriceVolEstimator` 等）。

## 事件流（handle_order_book 为例）
1. 上层传入 **已应用 deltas 的簿引用**：`handle_order_book(ts_ns, &book, inventory_qty)`（AlphaEngine 不再持有簿，也不再调用 `apply_deltas`）。
2. 特征状态更新：按输入标签对特征子集调用 `on_book`/`on_trade` 回调。
3. 采样判定：`SamplePolicy::should_sample` 根据时间/计数节流 + 可选 mid/inventory 阈值（`TriggerLogic::{Any,All}`）决定是否构建样本；冷启动输出由 `OutputPolicy` 处理。
4. 特征写入：`write_features` 读取每个特征 `value()` 填入 `feature_buf`，调用 `model.predict`，`last_alpha_bps` 更新。
5. 入队待标注样本：Labeler 保存 `(ts_ns, mid, features)`，溢出时返回错误。
6. 标签出队与训练：**每个事件**调用 Labeler（全量 mid feed），当 `ts_now - sample.ts >= lag_ns` 就用当前 mid 计算 `((mid_t - mid_0) / mid_0) * 1e4 bps`，由 `Trainer::on_labeled`（默认 `RlsTrainer` + `UpdatePolicy`）决定是否更新并调用 `model.update`。

`handle_trade` 复用了同样的预测/训练逻辑；默认特征仅标注 `BOOK`，需要交易/报价特征时在注册表里标注 `TRADE`/`QUOTE`。

## 采样策略（SamplePolicy / SamplePolicyConfig）
- 触发条件：`time_stride_ns`（0=关闭）、`count_stride`（0=关闭）、可选 `mid_move_bps`、`inventory_delta`，用 `trigger_logic` 组合。
- 状态：`last_trigger_ns`、`last_trigger_mid`、`snapshots_since_last` 由 Engine 维护。
- 绑定字段映射：`predict_*`、`predict_trigger_logic` 来自 `AlphaEngineParams`。

## 输出策略（OutputPolicy）
- 冷启动：`updates < min_updates_for_output` 时输出 0，样本仍进入 Labeler。
- 绑定字段映射：`min_updates_for_output` 来自 `AlphaEngineParams`。

## 训练器与更新策略（Trainer / UpdatePolicyConfig）
- 标签定义：滞后 mid 收益，单位 bps；lag 由 Labeler 控制，mid<=0 的样本直接跳过。
- 节流与过滤：按 `min_update_interval_ns`（时间节流）、`count_stride`（计数节流）、`sample_rate`（LCG 抽样）决定是否训练。
- 裁剪与过滤：`label_clip_bps` 做绝对值裁剪，`label_min_abs_bps` 做弱标签过滤，`mid_required` 控制 mid<=0 是否跳过。
- 状态：`last_update_ns`、`since_last`、`rng_state`；`rng_state` 为内置 LCG，避免额外 RNG 依赖。

## 默认特征（features.rs）
- 注册表由宏表生成；`lookup_feature` 用于校验名称并返回 `Inputs` 标签，`build_feature` 返回 `(Feature, Inputs)`。
- 引擎根据 `Inputs` 维护 `book_idx/trade_idx/quote_idx`，只对对应子集调用回调，避免触发未实现的 `Indicator` 默认方法。
- 内置特征（默认 `["imbalance", "micro_skew", "sigma_rel"]`）：
  - `imbalance`：基于 `BookL1Factors`，`(bid_qty - ask_qty) / (bid_qty + ask_qty)`，无市场时输出 0。
  - `micro_skew`：`(microprice - mid) / tick_size`，tick 小于 1e-9 时会被钳制。
  - `sigma_rel`：`BookMidPriceVolEstimator::sigma_rel()`；若样本不足则回退 `base_sigma`。
- 新特征步骤：在 `define_features!` 宏表添加条目，声明 `name`、`variant`、`inputs`、`init`（必要时绑定 `FeatureConfig`），确保名字能被 `lookup_feature` 找到（`-` 会自动转 `_`）。仅在实现了对应回调时才标注 `TRADE/QUOTE`。

## 模型接口与默认 RLS（models/rls.rs）
- `AlphaModel`：`predict(&[f64]) -> bps`、`update(&[f64], label_bps)`、`dimension()`、`weights()`。
- `weights()` 仅对在线可解释模型有意义；离线/不可解释 Predictor 不暴露权重，若用 `SwappableModel` 适配则 `weights()` 为空，语义由调用方负责。
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

## 离线模型热切换示例（简化）
```rust
use std::sync::Arc;
use nautilus_aurora::alpha::{
    AlphaEngine, ArcSwapModelHandle, InMemoryModelRegistry, ModelEntry, ModelMetadata,
    NoopTrainer, StaticPredictor, SwappableModel,
};

// 初始 predictor + handle
let handle = Arc::new(ArcSwapModelHandle::new(Arc::new(
    StaticPredictor::new(offline_model, "v1"),
)));
let model = SwappableModel::new(handle.clone());
let trainer: Box<dyn nautilus_aurora::alpha::Trainer<_>> = Box::new(NoopTrainer::new());
let mut engine = AlphaEngine::new_with_model_and_trainer(
    lag_ns, tick_size, i_max, model,
    time_stride_ns, count_stride, min_updates_for_output,
    label_queue_len, base_sigma,
    PredictPolicyConfig::default(),
    Some(features),
    trainer,
)?;

// 注册新模型并切换
let mut registry = InMemoryModelRegistry::new();
registry.register(ModelEntry {
    metadata: ModelMetadata {
        version: Arc::from("v2"),
        feature_schema_hash: Arc::from(schema_hash),
        model_kind: Arc::from("onnx"),
        created_at_ns: ts_ns,
        notes: None,
    },
    predictor: Arc::new(StaticPredictor::new(new_offline_model, "v2")),
})?;
registry.set_current("v2")?;
registry.apply_current_checked(handle.as_ref(), schema_hash)?;
engine.set_model_version("v2", true);
```

## 扩展与注意事项
- AlphaEngine 不再持有簿；调用方负责维护唯一簿、应用 deltas，并传入引用。
- tick_size/base_sigma 均会被钳到非负，避免无效输入导致 NaN。
- Labeler 队列长度由 `label_queue_len` 控制；超长会返回错误，避免静默丢样。
- mid<=0 时预测直接返回上一值，更新侧在 `mid_required`=true 时跳过。
- 离线模型可用 `SwappableModel` + `NoopTrainer` + `ArcSwapModelHandle`；引擎侧仍使用统一的 `AlphaEngine`。
- metrics 按 `model_version` 分桶；可用 `set_model_version(version, reset)` 控制版本并选择是否重置当前桶。
- `feature_names()` 可用于计算特征契约哈希，配合 `ModelRegistry::apply_current_checked` 做版本一致性校验。
- 如需新策略字段，请保持默认值等价于旧行为，避免破坏 Python 侧兼容。
- 性能：核心路径无分配（特征向量预分配），策略/特征为内联函数；当前 metrics 仅含在线相关性统计，触发/更新原因尚未计数。

## 测试与验证
- `engine/mod.rs`：覆盖维度校验、共享状态复用、trade 触发、mid_move 阈值、标签裁剪等。
- `models/rls.rs`：RLS 参数校验、维度 mismatch、限幅、收敛性。
- 运行：`cargo test -p nautilus-aurora alpha::engine`
- 运行：`cargo test -p nautilus-aurora alpha::models::rls`

## 文档位置
- 详细设计放在本目录（贴近代码便于同步演进）。
- 上层 crate 级介绍可在 `crates/aurora/README.md` 链接到本文件，避免重复维护。
