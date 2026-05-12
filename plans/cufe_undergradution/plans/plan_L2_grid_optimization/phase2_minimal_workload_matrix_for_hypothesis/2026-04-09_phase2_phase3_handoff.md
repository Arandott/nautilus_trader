# Phase 2 To Phase 3 Handoff

Date: 2026-04-09

## 目标

这份 handoff 只回答一个问题：

- Phase 3 下一步最小、最合理的执行顺序是什么

## 核心判断

Phase 2 已经把 matrix 冻结成 `4` 组 family，所以 Phase 3 的第一优先级不是继续扩 workload，而是把这 `4` 组 family 变成可执行、可比较、可归档的结果。

## 建议执行顺序

### 1. 先跑现有可执行的 real workloads

先把下面两组用现有入口跑起来：

- `real_shallow_control`
- `real_deep_query_sparse_replay`

原因很简单：

- 这两组不需要新增代码
- 它们能先回答“deep query alone 是否带来相对改善”
- 它们也能尽快检验 Phase 2 的参数是否合理

### 2. 再补 synthetic runner

紧接着实现一个最小 synthetic runner，服务下面两组：

- `synthetic_dense_contiguous_home_court`
- `synthetic_sparse_page_control`

这个 runner 至少要支持：

- 选择 book kind
- 配置 `levels_per_side`
- 配置 `price_pattern`
- 配置 `tick_step`
- 配置 `update / insert / delete` mix
- 配置 `query_depth`
- 配置 `query_interval`
- 导出 throughput / RSS / occupancy / query timing

## 对 synthetic runner 的最小要求

只做本任务真正需要的部分，不要一开始做成通用大框架。

最小 CLI 能力应包括：

- `--book`
- `--levels-per-side`
- `--price-pattern`
- `--tick-step`
- `--operations`
- `--update-ratio`
- `--insert-ratio`
- `--delete-ratio`
- `--query-depth`
- `--query-interval`
- `--output`

## Phase 3 之前不建议做的事

在 synthetic dense / sparse 对照跑通前，不建议优先投入下面几类工作：

- `PAGE_SIZE` sweep
- `best repair` 微优化
- `best_bid_ask` 常数微调
- 新增更多 replay 数据集
- 新增更多 synthetic family

原因不是这些方向永远不重要，而是：

- 当前最缺的不是更多候选优化
- 而是一个能公平回答路线问题的 workload 舞台

## 允许的早停判断

如果 Phase 3 很快发现下面情况，应允许尽早写下来，而不是硬做更多实现：

1. `real_deep_query_sparse_replay` 没有带来任何相对排名改善
2. synthetic dense case 难以构造出稳定、可信的高 occupancy
3. 即使 dense synthetic 成立，`grid` 仍没有出现可复现正信号

如果出现这些情况，后续更合理的动作是：

- 收缩优化范围
- 尽快进入结论整理

## 最小成功标准

Phase 3 至少应该先做到：

1. `real_shallow_control` 跑完并落盘
2. `real_deep_query_sparse_replay` 跑完并落盘
3. synthetic runner 最小版本可用
4. dense / sparse synthetic 对照各至少跑出一轮结果

达到这四条后，再决定是否进入真正的代码优化 pass，会比现在就直接改实现稳很多。
