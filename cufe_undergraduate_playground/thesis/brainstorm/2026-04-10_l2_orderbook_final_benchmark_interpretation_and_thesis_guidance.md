# L2 Order Book Final Benchmark Interpretation And Thesis Guidance

Date: 2026-04-10

## Purpose

本文档面向后续论文写作 agent，整理截至 `2026-04-10` 的最新横向评估结论，并给出推荐的论文表述口径。

这份文档重点回答四个问题：

- 最新 unified compare 到底说明了什么
- `baseline`、`L2TreeBook`、`L2VecBook`、`L2GridBook` 各自应如何定位
- 哪些结论适合写进论文，哪些表述应避免
- 论文叙事应该如何组织，才能把这轮工程工作写成一个完整研究闭环

说明：

- 本文档默认以
  `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10`
  作为当前最新 unified compare 结果目录。
- `L2GridBook` 的阶段性优化分析，使用
  `plans/cufe_undergradution/plans/plan_L2_grid_optimization/phase5_integrated_compare_final_conclusion/2026-04-10_phase5_optimization_final_conclusion.md`
  作为辅助证据。
- `L2VecBook` 的更新路径优化分析，使用
  `plans/cufe_undergradution/plans/plan_L2_vec_optimization/phase1_shift_cost_attribution_and_payload_compaction/2026-04-10_phase1_l2vec_payload_compaction_memo.md`
  作为辅助证据。

## Current Authoritative Benchmark Scope

当前最新 unified compare 的实验配置如下：

- dataset:
  `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit: `10_000_000` deltas
- repeats: `3`
- books: `baseline`, `l2tree`, `l2vec`, `l2grid`
- workloads:
  - `replay_only`
  - `replay_periodic_query(q=100)`
  - `replay_periodic_query(q=1000)`

对应摘要文件：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/summaries/comparison_summary.md`

## Final Benchmark Snapshot

### Replay Throughput

| Workload | baseline updates/s | l2tree updates/s | l2vec updates/s | l2grid updates/s |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 186535.20 | 239499.86 | 175552.72 | 190025.20 |
| `replay_periodic_query::q100` | 184806.10 | 235823.59 | 174228.36 | 189194.93 |
| `replay_periodic_query::q1000` | 185140.38 | 237262.84 | 175013.03 | 187935.21 |

### Replay Query Latency

| Workload | baseline avg query ns | l2tree avg query ns | l2vec avg query ns | l2grid avg query ns |
| --- | ---: | ---: | ---: | ---: |
| `replay_periodic_query::q100` | 3379 | 2139 | 757 | 4554 |
| `replay_periodic_query::q1000` | 5354 | 2605 | 1299 | 6249 |

### Peak RSS

| Workload | baseline MB | l2tree MB | l2vec MB | l2grid MB |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 52.09 | 32.60 | 30.66 | 206.18 |
| `replay_periodic_query::q100` | 52.09 | 32.53 | 30.64 | 205.97 |
| `replay_periodic_query::q1000` | 52.09 | 32.52 | 30.66 | 205.90 |

### Criterion Means

| Case | baseline ns | l2tree ns | l2vec ns | l2grid ns |
| --- | ---: | ---: | ---: | ---: |
| `update_existing_level` | 75.434 | 18.572 | 25.796 | 33.903 |
| `insert_new_level` | 262.523 | 74.574 | 62.791 | 362.330 |
| `delete_existing_level` | 211.580 | 81.300 | 66.397 | 244.803 |
| `best_bid_ask` | 20.287 | 17.877 | 32.818 | 57.513 |
| `top_10_query` | 109.093 | 77.699 | 18.247 | 208.064 |

## Recommended Engineering Interpretation

### 1. `L2TreeBook` is the default engineering winner

当前最稳的工程判断仍然是：

- `L2TreeBook` 是这四种方案中的综合最优默认实现

原因是：

- 它在三种 replay workload 中吞吐都最高
- 它的 query latency 显著优于 `baseline`
- 它的内存占用很低，和 `L2VecBook` 同量级
- 它不依赖特殊 workload 才成立

因此，论文里可以稳定写成：

`L2TreeBook` 在真实 `L2_MBP` 增量回放场景下提供了最好的综合工程平衡，是当前最适合作为默认实时维护结构的方案。

### 2. `L2VecBook` should be positioned as a factor-friendly structure

这轮 `L2VecBook` 最重要的结论，不是“它最终超过了 `L2TreeBook`”，而是：

- 它通过 payload compaction 明显改善了真实 replay 性能
- 但它的核心优势依然集中在连续深度读取和 top-k 查询

可以把这件事拆成两层写：

第一层是优化有效：

- 旧 authoritative 基线中，`l2vec replay_only` 约 `126391.43 updates/s`
- 最新 unified compare 中，`l2vec replay_only` 提升到 `175552.72 updates/s`
- `q100` 也从约 `127102.13` 提升到 `174228.36`

第二层是定位更清楚了：

- 它的 `top_10_query` 是四者中最好，约 `18.247 ns`
- replay 下的 periodic query latency 也是最好
- RSS 仍然最低一档，约 `30.6 MB`
- 但 end-to-end replay throughput 仍明显落后于 `L2TreeBook`

因此，推荐在论文里把 `L2VecBook` 定位为：

- 面向连续深度读取的因子计算友好结构
- 适合 `top-k imbalance`、累积深度、盘口形状、depth slope、microprice 变体等读多型因子
- 不宜表述为默认实时 `L2` 维护结构

推荐标准表述：

`L2VecBook` 在连续深度读取、top-k 深度扫描和局部盘口因子提取方面展现出明显优势，因此更适合作为因子计算友好的专用结构；但由于中部插删带来的动态维护成本，其并不适合作为默认的实时 L2 维护结构。

### 3. `L2GridBook` should be positioned as a dense/deep specialist candidate

这轮 `L2GridBook` 不应写成“失败原型”，更准确的写法是：

- 它不是当前默认工程方案
- 但它在 `density + depth` 同时成立时展现出条件性优势

需要明确两点：

- 最新 unified compare 里，压缩后的 `L2GridBook` 吞吐已经稳定超过 baseline
- 但它的 RSS 仍明显过高，且真实 sparse replay 下依然落后 `L2TreeBook`

结合 Phase 1 到 Phase 5 的阶段性结论，更推荐这样写：

- `grid` 路线本身不是错的
- 它的优势依赖高 page occupancy 和足够深的查询负载
- 它当前更适合作为 dense/deep 专项结构候选，而不是通用默认实现

推荐标准表述：

`L2GridBook` 在高 density、深查询负载下展现出条件性优势，但在真实稀疏 replay 与 sparse synthetic 对照中，其 page 固定成本仍导致总体经济性不如 `L2TreeBook`。一轮受控结构压缩虽然降低了 page 体积并改善了部分真实场景性能，但未改变其不适合作为默认工程方案的判断。因此，`L2GridBook` 更适合作为 dense/deep 专项结构候选，而非通用默认实现。

### 4. `baseline` should be treated as the general-purpose reference

`baseline` 不是本轮实验里的“差方案”，而是：

- 通用语义最完整的参考实现
- 用来说明“L2 专用化数据结构到底压掉了哪些通用负担”

在论文里建议把它写成：

- 通用订单簿语义的工程参考基线
- 不是针对纯 `L2_MBP` replay 最优化的结构

这样能避免论文给人一种“为了打败 baseline 而构造 baseline”的感觉。

## What The Thesis Should Actually Claim

不建议把论文主问题写成：

- 哪个结构绝对最快
- `grid` 是否必然优于 `tree`
- `vec` 是否最终能取代 `tree`

更好的论文问题是：

- 在纯 `L2_MBP` 场景下，面向不同访问模式的数据结构应如何设计
- `tree`、`vec`、`grid` 三种专用结构分别适合哪些 workload
- 面向实时维护与面向因子计算的结构目标是否应该分离

换句话说，论文主线不该是单一冠军叙事，而应是：

- 提出三种 L2 专用结构
- 给出统一 trait、统一 replay runner、统一 parity test 的可比框架
- 在统一 benchmark 下识别它们各自的工程适用边界

这是一个比“谁最快”更像论文的问题。

## Recommended Thesis Narrative

比较稳的叙事方式是：

1. 从通用 `OrderBook` 出发，说明纯 `L2_MBP` replay 存在专用化空间。
2. 分别构造 `L2TreeBook`、`L2VecBook`、`L2GridBook` 三种特化结构。
3. 用统一接口和统一 benchmark，对它们进行公平对比。
4. 通过阶段性诊断和优化，回答每种结构为什么会赢、为什么会输。
5. 最终不是给出“唯一正确结构”，而是给出“结构与 workload 的匹配关系”。

如果需要一句总括式描述，可以直接用：

本文工作的主要贡献，不在于宣称某一种 L2 数据结构对所有场景都最优，而在于构建了一套面向纯 `L2_MBP` 订单簿维护与查询的特化结构比较框架，并通过统一 benchmark 与阶段性诊断，识别了 `tree`、`vec`、`grid` 三类结构各自的优势场景与工程边界。

## Suggested Chapter-Level Positioning

如果写作 agent 需要压缩结构，建议至少保留下面几层：

### 1. Problem And Motivation

- 通用订单簿实现保留了逐订单、逐 level 内部容器等额外语义
- 对纯 `L2_MBP` replay 与因子计算，这些能力未必必要
- 因而存在用更轻结构替代的空间

### 2. Specialized Structures

- `L2TreeBook`: 实时维护友好、综合最稳
- `L2VecBook`: 连续读取友好、因子计算友好
- `L2GridBook`: dense/deep 专项候选

### 3. Evaluation Methodology

- 统一 trait
- parity test
- criterion
- replay runner
- 真实 replay + 周期查询 workload

### 4. Stage-Based Optimization Evidence

- `L2VecBook`：
  shift-cost attribution -> payload compaction -> replay 大幅改善
- `L2GridBook`：
  occupancy / page-cost attribution -> minimal workload matrix -> targeted compaction -> 条件性结论

### 5. Final Engineering Decision

- 默认实时维护方案：`L2TreeBook`
- 因子计算友好结构：`L2VecBook`
- dense/deep 专项候选：`L2GridBook`

## Statements To Avoid

下面这些写法不建议出现在论文正文里：

- `L2GridBook` 失败了
- `L2VecBook` 不适合真实市场
- `L2TreeBook` 只是因为保守才赢
- 论文目标是证明某结构绝对最快

更好的替代表述是：

- `L2GridBook` 的优势是条件性的，而非普遍成立
- `L2VecBook` 更适合作为因子计算友好结构，而非默认实时维护结构
- `L2TreeBook` 在当前真实 replay 配置下提供了最佳综合工程平衡

## Suggested Reusable Thesis Paragraph

如果写作 agent 需要一段可直接改写的总结段，可以从下面这段出发：

针对纯 `L2_MBP` 订单簿场景，本文在通用 `OrderBook` 基线之外实现并比较了三种特化结构：`L2TreeBook`、`L2VecBook` 与 `L2GridBook`。统一 benchmark 结果表明，`L2TreeBook` 在真实增量回放下取得了最优的综合性能与稳定性，因此适合作为默认实时维护结构；`L2VecBook` 虽然在更新吞吐上仍落后于 `L2TreeBook`，但其在连续深度读取、top-k 查询和低内存占用方面具有显著优势，更适合作为面向盘口因子提取的专用结构；`L2GridBook` 则在高 density、深查询负载下展现出条件性优势，但在真实稀疏 replay 中仍受到 page 固定成本约束，因此更适合作为 dense/deep 场景的专项候选结构。上述结果说明，L2 专用结构的优劣并非由单一理论复杂度决定，而与 workload 的深度、稠密度及读写模式密切相关。

## Recommended Figures And Tables

如果写作 agent 需要挑图表，优先级建议如下：

1. 一张四方案 unified compare 总表
   - 吞吐
   - query latency
   - RSS
2. 一张 `L2VecBook` 优化前后对比表
   - `updates/s`
   - `top_10_query`
   - `avg_shifted_bytes_per_delta`
3. 一张 `L2GridBook` 的 occupancy / page-cost 诊断图或表
4. 一张“结构定位表”
   - 默认实时维护
   - 因子计算
   - dense/deep 专项

## Bottom Line

截至当前版本，更适合交给论文写作 agent 的最终口径是：

- `L2TreeBook`：默认工程最优解
- `L2VecBook`：因子计算友好结构
- `L2GridBook`：dense/deep 专项候选
- `baseline`：保留完整通用语义的参考实现

这套工作最好的论文表达，不是“谁赢了全部场景”，而是：

- 本文构建并验证了多种 `L2` 专用结构
- 它们对应不同的工程目标
- 最终结论是“结构选择应服从 workload”，而不是“存在唯一普适最优结构”
