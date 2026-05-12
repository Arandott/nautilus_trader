# Phase 4 To Phase 5 Handoff

日期：2026-04-10

## 核心判断

Phase 4 已经足够回答“第二轮小规模结构优化值不值得继续”这个问题：

- 值得做，而且做完了
- 结论也已经出来了
- 但结论不是“继续在当前边界内优化就能把 grid 变成默认方案”

更准确的说法是：

- 这轮压缩证明 `grid` 的固定 page 成本确实过高
- 压缩 page 成本能改善真实 sparse replay 的吞吐和 RSS
- 但它同时带来了 dense/sparse synthetic query 退化
- `grid` 仍然没有跨过默认工程方案的门槛

## Phase 5 应如何收束

Phase 5 不建议再加实现工作，重点应该变成：

1. 固化最终结论
2. 整理证据链
3. 给出推荐的默认方案和专项结构定位

## 建议的最终表述

建议在最终结论里明确写成：

- `L2TreeBook` 仍是当前最稳妥的默认工程方案
- `L2GridBook` 有真实正信号，但这个正信号强依赖 `density + depth`
- Phase 4 的压缩优化降低了 page 固定成本，却没有消除 sparse-case 的结构性劣势
- 如果未来继续做 `grid`，应该按“dense/deep 专项结构”继续，而不是把它当作默认替代者

## 建议保留的证据链

Phase 5 最终文档里至少保留下面四段证据：

1. Phase 1 的 occupancy 归因
   - 真实 replay 中 populated page 几乎是 `1 page = 1 level`
2. Phase 3 的路线判断
   - dense synthetic 出现正信号，sparse synthetic 不成立
3. Phase 4 的结构压缩结果
   - `grid_page_size_bytes` 从 `5152` 降到 `4128`
   - 真实 sparse replay 的 throughput / RSS 有改善
4. Phase 4 的停损证据
   - sparse synthetic 没被修好
   - dense synthetic query 反而变慢

## 不建议继续做的事

在进入 Phase 5 之前，不建议再继续：

- `PAGE_SIZE` 扫参
- `best repair` 常数微调
- 扩更多 replay workload
- 扩更多 synthetic family

原因不是这些方向永远没价值，而是：

- 当前任务的问题已经回答到了足够清楚
- 继续做只会把任务边界推大，而不会显著改变最终结论

## 如果未来要开新任务

如果之后想继续 `grid`，更像是一个新任务，而不是当前计划的延长线。新的任务方向可以是：

1. 设计真正的 compact sparse page
2. 引入 occupied-slot list / hybrid sparse page
3. 把 dense page 和 sparse page 区分成两套 representation

这些方向都超出了当前 Phase 4 的“小规模受控优化”边界。
