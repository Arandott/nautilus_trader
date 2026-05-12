# Phase 3 To Phase 4 Handoff

Date: 2026-04-09

## 核心判断

Phase 3 已经把最重要的路线问题回答到足够清楚的程度：

- `grid` 的正信号确实存在
- 但它和 dense page occupancy 强绑定
- deep query 自己并不能让真实 sparse replay 里的 `grid` 自然翻盘

因此 Phase 4 的任务不应再是“惯性继续优化”，而是先做一次明确决策。

## Phase 4 应回答的问题

### 1. 是继续做第二轮优化，还是尽快收束为结论

当前有一个真实的 `conditional yes`，所以继续做第二轮优化是有理由的。

但这个理由必须被限定为：

- 继续优化 dense/deep 专门结构
- 或者继续验证能否显著降低 sparse-case 惩罚

而不是重新回到“默认工程方案一定要换成 grid”这个前提。

### 2. 第二轮优化的主战场应该放在哪里

根据 Phase 1 和 Phase 3 的合并证据，最优先的候选项仍然是：

1. 压缩 slot payload
   - 优先评估去掉 slot 内完整 `Price`
   - 让 `price = base_tick + slot` 成为派生值

2. 改善 sparse-case economics
   - 例如 small-page / compact occupied-slot / hybrid sparse-page
   - 重点不是让 dense case 更快一点，而是别让 sparse case 退化得这么惨

3. 只在上面两类之后，再考虑 `PAGE_SIZE` sweep

## 不建议优先做的事

在进入第二轮优化前，下面这些方向仍不建议排到最前面：

- 只做 `best repair` 微优化
- 只做 `best_bid_ask` 常数微调
- 继续在真实 sparse replay 上抠小常数，期待 `grid` 自然超过 `l2tree`

## 推荐的 Phase 4 路径

如果决定继续：

1. 先挑一个低到中风险的结构压缩项
2. 每次只做一个小改动
3. 每个改动后至少复测：
   - `real_shallow_control`
   - `synthetic_dense_contiguous_home_court`
   - `synthetic_sparse_page_control`

如果决定不继续：

1. 明确写下 `conditional yes` 结论
2. 把 `L2TreeBook` 继续作为默认工程方案
3. 把 `L2GridBook` 定位成候选专项结构，而不是默认替代者

## 允许的早停判断

Phase 4 如果出现下面情况，应允许尽早停下：

1. 第一轮结构压缩后，dense case 改善有限，但 sparse case 仍然没有实质改善
2. 继续推进需要大规模改写 page representation，已经超出当前任务边界
3. 结论已经足够清楚，但只是“不适合作为默认方案”

这三种情况都不是失败，而是有效结论。
