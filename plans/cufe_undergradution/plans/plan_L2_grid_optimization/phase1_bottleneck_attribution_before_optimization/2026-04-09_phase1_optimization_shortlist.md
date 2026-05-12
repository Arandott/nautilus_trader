# Phase 1 Optimization Shortlist

Date: 2026-04-09

## Decision Rule

phase1 的排序标准不是“看起来可能更快”，而是三件事一起看：

- expected upside
- implementation risk
- validation cost

只有同时满足“收益足够大”且“能被下一阶段验证”的候选项，才值得进后续 phase。

## Shortlist

| Candidate | Keep / Drop | Expected upside | Risk | Validation cost | Why |
| --- | --- | --- | --- | --- | --- |
| 引入更适合 sparse replay 的 page 表示，例如 compact occupied-slot payload、small-page、hybrid sparse-page | `Keep` | `Very high` | `High` | `Medium` | 当前主问题是 `1 page = 1 level`，不先动 page 表示，就很难从根上降 RSS 和 insert/delete 常数 |
| 去掉 slot 内完整 `Price`，把 price 改为 `base_tick + slot` 派生，仅保留更小 payload | `Keep` | `Medium` | `Medium` | `Low` | `Option<GridLevel>` 现在高达 `80 bytes`，slot payload 压缩是当前最直接的 page body 减重手段 |
| 对 `PAGE_SIZE` 做有边界的 sensitivity sweep，例如 `8 / 16 / 32 / 64` | `Keep` | `Medium` | `Low` | `Low` | 这能帮助判断 64 是否明显偏大，但它不是第一顺位，因为 occupancy 先天已经崩成 `1` |
| 设计 dense / sparse 对照 workload 与 deep-query-heavy workload | `Keep` | `High` | `Low` | `Medium` | 这不是代码优化，但它是判断 `grid` 路线是否有主场的必要步骤，应该在 phase2 优先完成 |
| 只做 `BTreeMap<PageId, GridPage>` 的容器微调 | `Drop as first pass` | `Low to medium` | `Low` | `Medium` | 当前 page index 已经近似退化成 per-level tree，单换容器不能解决 page body 爆炸 |
| 只做 delete-best repair 微优化 | `Drop as first pass` | `Low` | `Low` | `Low` | criterion 显示 delete 弱，但根因是“删一个 level 经常等于删一个 page”，不是 repair 细节本身 |
| 只做 best cache / best query 微优化 | `Drop as first pass` | `Low` | `Low` | `Low` | `best_bid_ask` 的确偏慢，但 phase1 已经证明这不是主矛盾 |
| 在当前 authoritative replay workload 上继续打磨常数，期待 `l2grid` 自然超过 `l2tree` | `Drop` | `Very low` | `Low` | `High` | 这个 workload 下 page occupancy 已经说明结构不匹配，再抠常数大概率收效有限 |

## Recommended Order

如果后续继续推进，我建议按下面顺序走：

1. 先做 phase2 workload matrix
   - 确认 dense contiguous pages 是否真实存在
   - 确认 deep query 是否会放大 `grid` 的潜在优势

2. 再做第一批结构压缩
   - 优先 slot payload 压缩
   - 再看是否需要进一步调整 sparse page 表示

3. 最后才做常数优化
   - `PAGE_SIZE` sweep
   - best/delete 微调

## What Should Not Happen Next

phase1 之后最不推荐的路径是：

- 直接开始大规模改 `best repair`
- 只盯着 `PAGE_SIZE`
- 在当前 shallow replay workload 上继续 harden 一个显然对 sparse occupancy 不友好的 page 结构

如果这么做，最可能得到的不是“grid 终于赢了”，而是：

- 代码更复杂
- benchmark 稍微好一点
- 但主结论仍然不变

## Bottom Line

phase1 的 shortlist 很清楚：

- 值得保留的是“改变 sparse-page economics”的东西
- 不值得优先投入的是“在错误 occupancy 假设上继续抠常数”的东西
