# Correctness Specification

日期：2026-03-23

## 1. 目标

本文档定义后续优化实现的正确性标准。

原则只有一句话：

**性能比较之前，先证明结果没有变。**

## 2. 参考实现

在本课题中，默认参考实现为原生 `nautilus_trader` 的：

- `OrderBook(BookType::L2_MBP)`

核心入口包括：

- `crates/data/src/engine/book.rs:68`
- `crates/model/src/orderbook/book.rs:353`
- `crates/model/src/orderbook/book.rs:301`

后续所有 `L2TreeBook / L2VecBook / L2GridBook` 都应在相同输入下与该 baseline 做一致性比较。

## 3. 输入一致性要求

比较必须基于同一份原始 delta 流。

这意味着：

- 使用相同数据集
- 使用相同解析逻辑
- 使用相同的 snapshot / clear 语义
- 使用相同的 delta 顺序

如果某次比较在输入适配层就不一致，那么该次结果无效。

## 4. 比较层次

正确性检查分为四层。

## 4.1 单步状态一致性

在抽样检查点上，比较：

- best bid price
- best ask price
- best bid size
- best ask size
- bid top-N
- ask top-N

这是最先落地的一层。

## 4.2 指定价位一致性

对采样 price 比较：

- 某个 bid price 的 quantity
- 某个 ask price 的 quantity

这层对 `L2GridBook` 尤其重要。

## 4.3 最终状态一致性

全量 replay 结束后比较：

- bid 全部 level
- ask 全部 level
- 最终 sequence
- 最终 `ts_last`

## 4.4 派生特征一致性

在 feature extraction workload 中比较：

- spread
- midpoint
- top-k imbalance
- microprice

## 5. 比较对象与格式

建议最终统一成“按 side 的 price-size 序列”做比较，而不是比较内部对象结构。

也就是说，无论内部是：

- `OrderBook`
- `L2TreeBook`
- `L2VecBook`
- `L2GridBook`

对外比较时都先转成：

- bid: `[(price, size), ...]`
- ask: `[(price, size), ...]`

这样可以避免：

- 内部容器不同
- 调试打印格式不同
- 结构体字段不同

导致的伪差异。

## 6. 比较规则

## 6.1 价格比较

优先按内部原始 price 值做精确比较。

如果某个实现暂时只能导出字符串或 decimal，则要求：

- 相同精度
- 相同归一化规则

不允许只做“看起来差不多”的浮点比较。

## 6.2 数量比较

优先按内部 raw quantity 做精确比较。

如果必须经过 decimal 或字符串层，则需要保证：

- 相同 precision
- 无额外舍入

## 6.3 派生特征比较

对于从 price-size 直接推导出的特征：

- 若实现共用相同数值类型，则要求精确相等
- 若通过不同语言层或浮点中间层计算，则单独定义一个很小的容忍误差

建议 Phase 0 先尽量采用精确比较。

## 7. 抽样与检查频率

为了兼顾性能与可定位性，建议分两档执行。

### 7.1 调试档

用于小样本调试：

- 每条 delta 都比较

### 7.2 全量档

用于全日数据：

- 每 `1000` 条 delta 抽样比较一次
- 每次 snapshot 边界比较
- 每个实验结束时比较最终状态

必要时可再补：

- 每 `100` 条比较一次的高精度档

## 8. top-N 一致性规则

建议固定比较这些深度：

- top-1
- top-5
- top-10
- top-20

对于每个深度，同时比较：

- 价位顺序
- 每档 quantity

只比较最佳价是不够的，因为某些实现可能在 deeper levels 出错但不影响 top-1。

## 9. 失败记录规范

一旦发现不一致，至少记录：

- 数据集路径
- delta 索引
- sequence
- `ts_event`
- 当前 delta 内容
- baseline top-N
- candidate top-N
- 抽样 price 对比结果

建议输出位置：

- `cufe_undergraduate_playground/results/comparisons/raw/`

建议格式：

- `json`
- `jsonl`
- `markdown` 摘要

## 10. 已知需要特别关注的边界情况

以下情况应被单独覆盖：

- snapshot / clear 起点
- 删除不存在 level
- update 到零数量
- 同价位重复更新
- bid / ask 两侧边界价位

另外需要注意：

`apply_delta_unchecked` 对未知 `order_id` 的 `Update/Delete` 有跳过路径，见：

- `crates/model/src/orderbook/book.rs:307`

因此 correctness harness 比较的是：

“在相同 baseline 语义下是否一致”

而不是：

“是否符合某个理想化的交易所协议解释”

## 11. Pass 标准

一个实现被认为正确，至少需要满足：

- 抽样检查点的 best bid/ask 全部一致
- 抽样检查点的 top-N 全部一致
- 指定价位 quantity 全部一致
- 全量 replay 结束后的最终 book 状态一致
- 派生特征在既定规则下全部一致

只要任何一项失败，该版本都不能进入正式性能比较。

## 12. Phase 0 最小正确性集合

Phase 0 先不需要做最重的全覆盖检查，最小集合即可：

- `best bid/ask`
- `top-10`
- 最终状态
- 两侧若干采样 price 的 quantity

这套最小集合已经足以支持：

- baseline 自检
- 后续 `L2TreeBook` 第一轮验证
