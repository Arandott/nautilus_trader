# L2Grid Optimization Agent Prompt

Date: 2026-04-09

## Your Mission

你将接手 `L2GridBook` 的下一阶段优化工作。

当前仓库已经有三种面向 `L2_MBP` 的特化订单簿实现：

- `L2TreeBook`
- `L2VecBook`
- `L2GridBook`

其中：

- `L2TreeBook` 是当前综合表现最好的工程实现
- `L2VecBook` query 很强，但真实 replay 最慢
- `L2GridBook` 已经完成了真正的 grid 化实现，但当前性能和内存表现都不理想

你的任务不是“强行证明 grid 一定赢”，而是：

1. 搞清楚当前 `L2GridBook` 为什么没有跑赢 `L2TreeBook`
2. 找到并实现一批高价值优化
3. 设计能凸显 grid 结构潜在优势的 workload，而不是只沿用当前偏浅层的 workload
4. 用结果回答一个关键问题：
   `L2GridBook` 是否更适合更深、更大、更稠密或更强调 deep-query 的 order book 工作负载？

如果最终答案是否定的，也要把这个结论讲清楚。

## Core Background

### Current architecture status

`L2GridBook` 当前已经不是早期的 `BTreeMap<tick, level>` 原型，而是真正的 chunked sparse-grid：

- side -> `SideGrid`
- `SideGrid` -> `BTreeMap<PageId, GridPage>`
- `GridPage` -> `[Option<GridLevel>; 64] + occupancy_bitmap`
- `price.raw -> (page_id, slot)` 使用 Euclidean division
- 每侧维护 `best_page + best_tick`

也就是说，当前版本已经完成了“结构正确性”的核心目标，但还没有兑现出强性能收益。

### Current authoritative results

当前仓库中只保留了一套最新、最完整的 comparison 结果：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000`

根据该结果：

- replay throughput:
  - `l2tree ~241k updates/s`
  - `baseline ~188k updates/s`
  - `l2grid ~182k updates/s`
  - `l2vec ~126k updates/s`
- peak RSS:
  - `l2tree ~31.5 MB`
  - `l2vec ~31.1 MB`
  - `baseline ~51.1 MB`
  - `l2grid ~248.9 MB`

因此，当前结论不是 “grid 已经赢了”，而是：

- `L2GridBook` 在当前 workload 下没有赢过 `L2TreeBook`
- `L2GridBook` 当前的内存代价异常高

### Current user insight you must take seriously

当前最重要的研究假设来自用户本人：

> `L2GridBook` 也许并不适合当前这种较浅、较轻的 workload；它可能更适合超大规模 order book，例如 500/1000 档，或者更强调 deep query / 深层维护 / 连续 tick 区间访问的工作负载。

你需要把这个 insight 变成可验证的 workload 设计，而不是停留在口头判断。

## Required Context To Read First

请先读下面这些文件，再开始动手。

### 1. High-level retrospective

- `cufe_undergraduate_playground/thesis/brainstorm/2026-04-09_l2_orderbook_engineering_status.md`

这份文档总结了三种结构的当前工程状态和最新结果，是你进入任务的最佳起点。

### 2. Current `L2GridBook` implementation

- `crates/model/src/orderbook/l2_grid.rs`

重点关注：

- `GridPage`
- `SideGrid`
- `PAGE_SIZE = 64`
- page bitmap scan
- best pointer maintenance
- delete-best repair
- `top_n_levels`

### 3. Comparison targets

- `crates/model/src/orderbook/l2.rs`
- `crates/model/src/orderbook/l2_vec.rs`
- `crates/model/src/orderbook/book.rs`
- `crates/model/src/orderbook/ladder.rs`
- `crates/model/src/orderbook/level.rs`

你需要明白：

- `L2TreeBook` 为什么当前这么强
- `L2VecBook` 为什么 query 强但 replay 弱
- baseline 到底多背了哪些通用语义负担

### 4. Benchmark and replay entry points

- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`
- `crates/adapters/tardis/tests/l2_book_parity.rs`
- `crates/adapters/tardis/tests/l2_vec_book_parity.rs`

你需要基于这些入口决定：

- 现有 benchmark 是否足以凸显 grid 的潜在优势
- 需要新增哪些 benchmark case
- 需要新增哪些 replay workload 配置

### 5. Existing implementation note

- `plans/cufe_undergradution/implementation/phase3/2026-03-24_phase3_l2gridbook_devlog.md`

这份 devlog 记录了当前 grid 结构的设计动机和验证路径。

### 6. Latest authoritative results

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/criterion_summary.json`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/runner_summary.json`

## Task Goals

你的目标分为两个并行方向。

### Goal A: Optimize the current implementation

请对当前 `L2GridBook` 做真正有根据的优化，而不是盲改。

你需要回答：

1. 当前 `L2GridBook` 的主要瓶颈是什么？
2. 是 page 结构太重，还是 page 索引太贵，还是页内表示不够紧凑？
3. 是 `PAGE_SIZE=64` 不合适，还是 best repair / traversal 的实现方式有隐藏成本？
4. 为什么它的 peak RSS 会远高于 `L2TreeBook` 和 `L2VecBook`？

优化方向可以包括，但不限于：

- 更紧凑的 `GridPage` 表示
- 降低 `Option<GridLevel>` 带来的空间/分支成本
- 重新审视是否必须在 page 内保存完整 `Price`
- page 元数据瘦身
- `PAGE_SIZE` 调优或参数化实验
- 减少跨页 traversal 成本
- 减少 best pointer 维护成本
- 减少不必要的 allocation / copying / branching

但请记住：

- 不要为了优化而破坏 `L2BookOps` 语义
- 不要仅靠“想象中更快”来改
- 每个重要改动都要能被 benchmark 或 profile 支持

### Goal B: Design workloads that can fairly test grid advantages

你必须认真处理这个问题：

> 当前 benchmark / replay workload 是否天然偏向 `L2TreeBook`，而没有给 `L2GridBook` 一个公平发挥的舞台？

请至少探索下面几类 workload：

1. 更深的 query depth
   - `top_100`
   - `top_500`
   - `top_1000`

2. 更深的 periodic query replay
   - 不仅是 `q=100` / `q=1000`
   - 还要考虑 query depth 本身变深，而不是只改变 query 频率

3. 更大 active book depth 的 synthetic workload
   - 例如 500 档、1000 档长期活跃
   - 相邻 tick 高密度分布
   - dense contiguous price regions

4. 稠密 vs 稀疏 price distribution 对照
   - contiguous dense pages
   - highly sparse pages

5. update/query mix 的变化
   - query-heavy
   - deep-query-heavy
   - mostly top-of-book
   - wide-book maintenance

你不一定要把所有组合都做成大而全矩阵，但至少要设计出几组能回答核心 hypothesis 的 workload。

## Deliverables

任务完成时，你至少需要交付：

1. 一份 bottleneck / measurement memo
   - 定量回答当前主要瓶颈来自哪里
   - 定量回答 peak RSS 为什么异常高
   - 至少覆盖 page footprint、page occupancy / density、update/query 热点、候选优化优先级

2. 代码改动
   - 若你认为存在明确优化机会，就实现它

3. workload / benchmark 改动
   - 增加能测试 grid 假设的 benchmark 或 replay workload

4. 一份结果总结
   - 明确写出哪一组结果是最新 authoritative 结果
   - 明确写出 `L2GridBook` 是否在某类 workload 下体现优势
   - 明确给出运行命令、配置、结果目录

5. 一份结论性判断
   - `L2GridBook` 是否适合作为“更深大规模 order book”的专门结构？
   - 如果仍然不适合，最可能的原因是什么？

## Constraints

请遵守这些约束：

1. 不要改坏 correctness
   - parity 是硬约束

2. 保持接口兼容
   - `L2BookOps`
   - replay runner
   - benchmark harness

3. 不要把任务变成大规模无边界重构
   - 重点是 `L2GridBook` 优化和 workload 设计

4. 不要用“只看单个 microbenchmark”的方式得出结论
   - 必须结合 replay 结果

5. 不要为了让 `grid` 好看而挑选失真的 workload
   - workload 要能自圆其说
   - 要能回答“什么场景下 grid 真的有价值”

## Validation Expectations

至少保证下面这些检查通过：

- `cargo test -p nautilus-model l2_grid --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo test -p nautilus-tardis --test l2_book_parity`

如果你新增了 benchmark / replay workload，也要给出对应的运行命令和结果目录。

另外请遵守以下验证节奏：

- 每轮重要优化之后，至少跑一组 smoke replay 或 targeted benchmark，避免只看单点 microbenchmark 就继续堆改动
- 只有在 correctness、smoke result、目标 workload 表现都没有明显恶化的前提下，才进入下一阶段
- 最终只能指定一套最新 authoritative 结果目录，避免多套结果并存导致结论漂移

## What Good Work Looks Like

好的交付不是“我做了一些微调”，而是下面这种级别：

- 我定位了 `L2GridBook` 当前慢和占内存大的真正原因
- 我做了几项高价值优化，并解释为什么这样改
- 我新增了几组能测试 deep-book hypothesis 的 workload
- 我用结果说明：
  - `grid` 在哪些场景仍然不行
  - 或者 `grid` 在哪些场景开始显出优势

最终你要交付的是“判断力 + 证据”，不是单纯代码量。

## Phased Execution Plan (with Exit Criteria)

请按 phase 推进，不要把测量、workload 设计、实现优化、结论写作混成一个大杂烩。

### Phase 0: Context Freeze + Baseline Lock

目标：

- 读完 required context
- 明确当前唯一 authoritative 结果集
- 用自己的话复述当前结论和核心 hypothesis

本阶段应完成：

- 整理当前 `L2TreeBook`、`L2VecBook`、`L2GridBook` 的角色分工和已知 trade-off
- 确认当前 replay / criterion / parity 入口
- 写一个简短 baseline note，明确当前最可信结论是什么、哪些问题仍未回答

Exit criteria：

- 你能清楚说明当前为什么 `L2TreeBook` 暂时领先
- 你能清楚说明当前 workload 为什么不足以直接判定 grid 路线失败
- 你已经明确记录“当前 authoritative 结果目录”以及后续用于替换它的规则

### Phase 1: Bottleneck Attribution Before Optimization

目标：

- 在不盲改的前提下，定位 `L2GridBook` 慢和占内存大的主要原因

本阶段应完成：

- 分析 `GridPage` / `SideGrid` 的内存结构和 page-level 开销
- 观察真实或准真实 workload 下的 page occupancy / density 特征
- 对 update / insert / delete / best / top-N 路径做针对性测量
- 给出候选优化项，并按“预期收益 / 风险 / 验证成本”排序

Exit criteria：

- 你能用证据回答 Goal A 的四个问题，而不是只给猜测
- 你至少定位出一个主要内存来源和一个主要性能来源
- 你已经形成一个有限、可执行的优化 shortlist
- 如果做不到这些，就不要进入 Phase 3；先补测量

### Phase 2: Minimal Workload Matrix For The Hypothesis

目标：

- 设计一组足够小、但足够回答问题的 workload matrix

本阶段应完成：

- 至少覆盖真实浅层 workload、真实 deep-query workload、dense synthetic workload、sparse synthetic 对照 workload
- 明确每组 workload 想验证什么，不要只是参数排列组合
- 优先建立少量 canonical case，而不是一开始铺满大矩阵

Exit criteria：

- 每组 workload 都能回答一个明确问题
- workload 数量已经被控制在“足以决策”而不是“越多越好”
- 你已经写清每组 workload 的运行入口、主要参数、结果输出目录命名方式

### Phase 3: Targeted Optimization Pass

目标：

- 只实现那些已经被证据支持的高价值优化

本阶段应完成：

- 优先尝试低风险、高信息量的优化
- 每次只引入少量改动，确保能归因效果
- 每个重要改动后立即做 correctness + targeted measurement

Exit criteria：

- 每个保留下来的优化都能说清“为什么这样改”
- 每个保留下来的优化都至少在一个关键指标上带来可复现改善，或显著澄清了路线限制
- 没有优化只是“让 microbenchmark 更好看”却拖累 replay / RSS 而被默认保留

### Phase 4: Conditional Second Pass Or Early Stop

目标：

- 决定是否值得继续第二轮优化，而不是惯性往下做

本阶段应完成：

- 基于 Phase 1-3 的证据判断：当前更像是“实现仍有明显改进空间”，还是“路线本身不占优”
- 只有在出现明确正信号时，才继续第二轮有针对性的优化

Exit criteria：

- 如果 grid 已在某类合理 workload 下出现可复现优势，可以继续做第二轮强化
- 如果 grid 在合理 workload 下仍无优势，且主要问题已接近结构性限制，应停止深挖并转向结论整理
- 不能因为“已经投入很多”而继续无边界优化

### Phase 5: Integrated Compare + Final Conclusion

目标：

- 统一完成最终比较、结果归档、结论写作

本阶段应完成：

- 跑完整的最终 comparison 组合
- 只保留一套最新 authoritative 结果目录
- 写清楚 `grid` 在哪些 workload 下赢、输、或没有明显差异
- 写清楚原因更偏实现问题，还是路线问题

Exit criteria：

- 你已经指定唯一 authoritative 结果集
- 你已经给出 yes / no / conditional yes 的结论，而不是模糊表述
- 任何读者都能从你的文档里看出：grid 的价值边界在哪里

## Stop Rules / Escalation Conditions

出现下面任一情况时，请明确停下来并在文档中写出判断，而不是继续盲目扩张任务：

- 如果 Phase 1 之后仍无法回答主要瓶颈来自哪里，不要进入实现优化，先补测量
- 如果某项改动只改善 microbenchmark、却恶化 replay 或显著拉高 RSS，默认不保留
- 如果 workload 设计已经足够公平，但 `L2GridBook` 仍无法在任何合理场景体现可复现优势，需要允许负结论成立
- 如果继续推进需要大规模重构 page index / trait / runner 才可能看到信号，应明确说明这已经超出本任务边界
- 如果最终结论是 `L2TreeBook` 仍应作为默认工程方案，也要把这个结论作为有效交付，而不是失败

## Bottom Line

你真正要回答的问题不是：

- `L2GridBook` 能不能被再优化一点？

而是：

- `L2GridBook` 到底适不适合作为“更深、更大规模 L2 book”的专门结构？
- 如果适合，什么 workload 能证明它？
- 如果不适合，是实现问题，还是路线本身的问题？

请围绕这个问题组织你的全部工作。
