# Phase 5 Optimization Final Conclusion

日期：2026-04-10

## 结论范围

这份结论只收口下面这个问题：

- `L2GridBook` 这轮分阶段优化之后，是否应继续作为默认 `L2` 实现推进

这份文档不承担论文撰写任务，但会尽量把口径整理成后续可直接引用的形式。

## 最终结论

最终判断是：

- **`L2GridBook` 不适合作为当前默认工程方案的替代者。**
- **`L2GridBook` 在 `density + depth` 同时成立时，具有条件性优势。**
- **当前最稳妥的默认工程方案仍然是 `L2TreeBook`。**

更准确地说：

1. `grid` 的正信号是真实存在的
2. 但这个正信号并不是普遍成立
3. 它强依赖高 page occupancy 和足够深的 query 负载
4. 在真实 sparse replay 与 sparse synthetic 对照中，`grid` 的结构性成本仍然过高

## 证据链整合

### 1. Phase 0 和 Phase 2 保证了比较边界是可信的

这轮任务不是“先改代码再挑数据”，而是先固定了比较边界：

- baseline 被先冻结
- workload matrix 被限制在 4 组 canonical family
- 扩矩阵的条件被显式写死

这意味着后面的结论不是来自 cherry-pick，而是来自受控比较。

## 2. Phase 1 先回答了问题到底出在哪里

Phase 1 的核心归因是：

- `GridPage` 的静态固定成本过大
- 真实 replay 下 populated page 几乎退化成 `1 page = 1 level`

这一步很关键，因为它说明：

- `grid` 当前的问题不是“常数还没抠够”
- 而是 page representation 与真实 sparse workload 之间存在结构性错配

## 3. Phase 3 证明了 `grid` 的优势是条件性的

Phase 3 的 authoritative 结果回答得很清楚：

- 在真实 sparse replay 中，仅仅把 query 变深，并不能让 `grid` 自然翻盘
- 在 dense synthetic home court 中，`grid` 对 `l2tree` 出现了明确正信号
- 在 sparse synthetic control 中，这个正信号又消失了

因此，Phase 3 的核心判断不是“`grid` 更快”或“`grid` 更慢”，而是：

- `grid` 的优势强依赖 `density + depth`

这也是为什么本任务最终不是去证明“`grid` 必然优于 `tree`”，而是去回答“`grid` 的适用边界是什么”。

## 4. Phase 4 的结构压缩证明了固定成本确实可以被打掉一部分

Phase 4 只做了一轮低到中风险的结构压缩：

- slot 内不再存完整 `Price`
- 改为只存 `Quantity + price_precision`
- `Price` 在读取路径上由 `base_tick + slot` 派生

这轮改动带来了明确的静态收益：

- `grid_level_size_bytes`: `64 -> 48`
- `option_grid_level_size_bytes`: `80 -> 64`
- `grid_page_size_bytes`: `5152 -> 4128`

也就是说：

- 每个 page 的固定体积下降约 `19.9%`

在真实 sparse replay 上，这轮压缩确实带来了实际收益：

- `real_shallow_control`
  - `updates_per_sec`: `178,377.40 -> 190,175.17`，约 `+6.61%`
  - `peak_resident_mb`: `249.97 -> 206.13`，约 `-17.54%`
- `real_deep_query_sparse_replay (depth=500, q=100)`
  - `updates_per_sec`: `133,305.51 -> 160,245.90`，约 `+20.21%`
  - `avg_query_ns`: `104,170 -> 103,915`，几乎不变
  - `peak_resident_mb`: `249.77 -> 206.16`，约 `-17.46%`

这说明：

- page 固定成本确实是个真问题
- 压缩 page 固定成本也确实能带来真实收益

## 5. 但 Phase 4 同时证明了“小修”不足以把 `grid` 变成默认方案

Phase 4 也给出了明确的停损证据：

- dense synthetic 下，`grid` 虽然仍快于 `l2tree`，但 deep query 明显变慢
- sparse synthetic 下，内存改善成立，但 runtime 没有被救回来
- 真实 sparse replay 中，`grid` 仍然没有超过 `l2tree`

换句话说，Phase 4 证明的是：

- 这轮压缩是“有效优化”
- 但它不是“决定性修复”

如果还想继续追 sparse-case economics，下一步就不再是当前任务边界里的小优化，而会变成：

- compact sparse page
- occupied-slot list
- hybrid sparse/dense page representation

这已经是下一轮新任务，而不是本轮 Phase 4 的延长线。

## 应如何给出最终判断

综合所有阶段之后，更合适的最终判断是：

### 默认实现判断

- 默认 `L2` 工程方案继续采用 `L2TreeBook`

原因：

- 它在真实 sparse replay 上表现更稳
- 它没有 `grid` 那么高的结构性 page 成本
- 它不依赖高 density 才成立

### `grid` 的定位判断

- `L2GridBook` 不应被表述为“失败原型”
- 更准确的定位是“dense + deep 专项结构候选”

原因：

- 它在 dense/deep 组合上有真实正信号
- 这说明路线本身不是错的
- 但它不适合作为当前通用默认实现

## 建议保留的标准表述

如果后续材料需要一句较正式、稳定的结论表述，建议使用：

`L2GridBook` 在高 density、深查询负载下展现出条件性优势，但在真实稀疏 replay 与 sparse synthetic 对照中，其 page 固定成本仍导致总体经济性不如 `L2TreeBook`。一轮受控结构压缩虽然降低了 page 体积并改善了部分真实场景性能，但未改变其不适合作为默认工程方案的判断。因此，`L2GridBook` 更适合作为 dense/deep 专项结构候选，而非通用默认实现。

## 后续使用说明

如果后续 agent 需要继续使用这份结论，建议注意下面两点：

1. authoritative 横评结果主要来自 Phase 3
   - 因为那一轮对 `baseline` / `l2tree` / `l2vec` / `l2grid` 都做了统一比较
2. Phase 4 是针对 `l2grid` 的增量验证
   - 它用来回答“结构压缩有没有价值”
   - 它不应用来替代整套横评结论

## 最终收口

到 Phase 5 为止，这轮 `L2 grid optimization` 已经足够收口：

- 研究问题已经回答清楚
- 优势成立的条件已经识别清楚
- 无效继续推进的边界也已经识别清楚

因此，本任务的最终建议是：

- 在当前计划内停止继续优化
- 保留 `L2TreeBook` 作为默认方案
- 将 `L2GridBook` 作为后续 dense/deep 专项结构研究的候选方向
