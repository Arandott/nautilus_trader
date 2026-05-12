# Baseline Overhead Hypotheses

日期：2026-03-23

## 1. 目标

本文档不直接给出结论，而是写清楚我们在实现优化之前，**预期 baseline 可能多花在哪些地方**，以及这些假设要如何被验证或证伪。

## 2. 总体判断

当前 baseline 并不是“完全没有 L2 优化”。

它已经具备：

- 按 price level 排序的 `BTreeMap`
- 直接从首 level 取 best bid / best ask 的查询路径

所以我们不应该预期所有指标都有巨大提升。更合理的预期是：

- 更新路径和 replay 吞吐可能有稳定的常数级收益
- 内存与容器开销可能下降
- best bid / ask、top-N 的收益可能相对有限

## 3. 开销假设表

| ID | 假设 | 代码证据 | 主要影响 | 预期由谁削减 | 验证方式 |
| --- | --- | --- | --- | --- | --- |
| H1 | `L2_MBP` 先做 `price -> synthetic order_id` 哈希，带来额外 CPU 开销 | `aggregation.rs:48`, `aggregation.rs:66` | `apply_delta`、full replay | `L2TreeBook` 及之后所有版本 | microbench `update_existing_level` + profile |
| H2 | `order_id -> BookPrice` 的 `cache` 让 update/delete 多了一层 `HashMap` 查找与维护 | `ladder.rs:121`, `ladder.rs:182`, `ladder.rs:265`, `ladder.rs:338` | `update_existing_level`、`delete_existing_level`、full replay | `L2TreeBook` 及之后所有版本 | microbench + profile + allocation 观察 |
| H3 | `BookLevel` 内部保存 `IndexMap<OrderId, BookOrder>`，对 L2 来说结构偏重 | `level.rs:39`, `level.rs:41` | replay 吞吐、峰值内存、查询路径中的对象间接访问 | `L2TreeBook` 及之后所有版本 | peak RSS、heap profile、full replay |
| H4 | 更新原语仍然是 `add/update/delete(order)`，不是 `upsert/delete(level)`，路径语义偏通用 | `book.rs:336`, `ladder.rs:264`, `ladder.rs:332` | replay 吞吐、现有 API 的分支成本 | `L2TreeBook` 及之后所有版本 | full replay + flamegraph |
| H5 | `BTreeMap + BookLevel + BookOrder` 的对象层次会影响 cache locality | `book.rs:66`, `ladder.rs:120`, `level.rs:41` | replay、`top_10_query`、feature extraction | `L2VecBook`、`L2GridBook` | full replay + query-heavy workload |
| H6 | 对价格离散 tick 的市场结构没有直接利用 | 现有路径无 tick-indexed 映射 | `quantity_at_price`、高密度区间 replay | `L2GridBook` | `quantity_at_price` + dense-window workload |

## 4. 一个重要的保守判断

### 4.1 `BookLevel.orders` 不是“很多订单”

在当前 `L2_MBP` 路径里，同一 price 会被映射到同一个 synthetic `order_id`。这意味着：

- 一个 L2 价位在正常情况下通常只会保留一个 synthetic order
- `BookLevel.orders` 更像“单元素容器”，而不是传统 L3 的逐单队列

因此我们不能把基线问题简单描述成：

“它在每个 level 里维护了很多订单，所以很慢”

更准确的说法是：

“它在 L2 场景下仍然保留了 order 容器、order 标识和 order 路径，这些抽象本身带来额外常数成本”

### 4.2 `size()` 求和不是最主要的热点

`BookLevel::size*` 系列函数确实会对 `orders.values()` 求和，但在 L2 常态下这通常只是在一个很小的容器上求和。

因此这里更像：

- 容器层间接访问成本
- 类型与对象层次成本

而不是“大规模求和算法成本”。

## 5. 我们不应过度期待的地方

以下几项在 baseline 中已经比较直接，因此不应一开始就期待巨大收益：

### 5.1 Best bid / ask

当前路径已经是：

`BTreeMap.iter().next() -> top() -> best_bid_price/best_ask_price`

对应：

- `ladder.rs:448`
- `book.rs:819`
- `book.rs:825`

所以如果优化后这项只提升很少，是符合预期的。

### 5.2 Top-N level 迭代

当前 `bids(depth)` / `asks(depth)` 已经直接对有序 level 做 `take(depth)`：

- `book.rs:561`
- `book.rs:566`

因此：

- `L2TreeBook` 对 top-N 的提升可能有限
- `L2VecBook` 和 `L2GridBook` 才更可能在 query-heavy workload 下体现明显优势

## 6. 与后续版本的映射

### 6.1 `L2TreeBook`

主要用于验证：

- 去掉 `synthetic order_id`
- 去掉 `cache`
- 去掉 `BookLevel.orders`
- 把更新原语改成真正的 level 语义

它主要回答：

“只做 L2 语义专用化，是否已经足够带来稳定收益？”

### 6.2 `L2VecBook`

主要用于验证：

- 更紧凑的内存布局
- 顺序扫描和 feature extraction 的 cache locality 优势

它主要回答：

“在已经 L2 专用化之后，布局优化还能再带来多少收益？”

### 6.3 `L2GridBook`

主要用于验证：

- 利用 tick 离散性后，是否能进一步提升 `quantity_at_price` 和密集区间更新性能

它主要回答：

“市场结构特征本身是否值得做成专门的数据结构？”

## 7. 验证策略

每个假设都不应只看一个总跑分，而要分两层验证：

### 7.1 Microbench

用于回答“为什么快”：

- `update_existing_level`
- `insert_new_level`
- `delete_existing_level`
- `best_bid_ask`
- `top_10_query`
- 可选 `quantity_at_price`

### 7.2 Real workload

用于回答“快在哪里有意义”：

- full-day replay
- replay + periodic top-N query
- replay + feature extraction

## 8. 证伪标准

如果后面 profiling 结果显示：

- `aggregation::price_to_order_id` 不是热点
- `cache` 访问占比很低
- full replay 的主要瓶颈不在订单簿而在 CSV 解析或对象构造

那我们就必须修正原始假设，而不是硬把收益归因给 `L2Book` 结构。

这份文档的意义就在这里：

它要求我们后续给出的是“被 profiling 支持的解释”，而不是“事后编出来的故事”。
