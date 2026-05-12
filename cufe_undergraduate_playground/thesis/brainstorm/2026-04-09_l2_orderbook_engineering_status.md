# L2 Order Book Engineering Status

Date: 2026-04-09

## Purpose

本文档记录当前工程中三种面向 `L2_MBP` 的订单簿特化实现现状：

- `L2TreeBook`
- `L2VecBook`
- `L2GridBook`

目标是为论文写作提供一个可直接引用的“工程实现阶段性结论”，重点回答：

- 三种结构分别怎么设计
- 它们相对 baseline 在工程上简化了什么
- 当前最新实测结果说明了什么
- 现阶段最可信的工程判断是什么

## Baseline: What We Are Replacing

当前仓库中的通用 baseline 是 `OrderBook`：

- 文件：`crates/model/src/orderbook/book.rs`
- 每侧结构：`BookLadder`
- `BookLadder` 内部：
  - `BTreeMap<BookPrice, BookLevel>`
  - `HashMap<OrderId, BookPrice>` cache
- `BookLevel` 内部还保留：
  - `IndexMap<OrderId, BookOrder>`
  - FIFO 顺序
  - exposure / size 等通用能力

这意味着 baseline 的优势是通用性强，可以同时服务更完整的订单簿语义；但对纯 `L2_MBP` 回放来说，它保留了按订单追踪和 level 内部容器等额外开销。

因此，这三种实验实现的共同目标，是把 baseline 压缩成“只关心 price level aggregate”的 L2 专用结构。

## Shared Interface

三种实现都挂在同一个 trait 上：

- `crates/model/src/orderbook/l2.rs`
- trait: `L2BookOps`

这意味着：

- benchmark 可以统一调用
- Tardis replay runner 可以统一切换
- parity test 可以直接对 baseline 做逐步对比

这也是当前实验可比性的基础。

## 1. L2TreeBook

代码位置：

- `crates/model/src/orderbook/l2.rs`

核心结构：

- `bids: BTreeMap<BookPrice, Quantity>`
- `asks: BTreeMap<BookPrice, Quantity>`

设计特点：

- 不再保存逐笔订单，只保存每个 price level 的 aggregate quantity
- 仍然保留 `BTreeMap` 的天然有序性
- buy/sell 的排序由 `BookPrice` 处理
- `best bid/ask` 直接取 map 首元素
- `top_n_levels` 直接遍历前 `depth` 个节点

工程评价：

- 这是三者里结构最简单、语义最稳定的一版
- 相对 baseline，它已经去掉了大部分与 `L2_MBP` 无关的通用负担
- 它依然有 per-level tree node 开销，但换来的是很低的实现复杂度和稳定的性能

当前结论：

- 它是目前真实 replay 表现最好的实现
- 也是当前最接近“工程可落地默认方案”的版本

## 2. L2VecBook

代码位置：

- `crates/model/src/orderbook/l2_vec.rs`

核心结构：

- `bids: Vec<(Price, Quantity)>`
- `asks: Vec<(Price, Quantity)>`

设计特点：

- 每侧 price level 按价格顺序连续存放
- level 定位通过 `binary_search_by`
- 插入新 level 使用 `Vec::insert`
- 删除 existing level 使用 `Vec::remove`
- `best bid/ask` 直接取 `first()`
- `top_n_levels` 直接拷贝前缀

工程评价：

- 它最强调连续内存和查询局部性
- 对 `best_bid_ask`、`top_n_levels` 这类只读查询非常友好
- 但在真实市场增量流中，只要频繁出现“中间插入/删除”，就要承受 `Vec` 搬移成本

当前结论：

- microbenchmark 中它的 query 表现很好
- 但 end-to-end replay 最慢
- 原因很可能不是查询，而是更新路径中的插入/删除搬移成本

## 3. L2GridBook

代码位置：

- `crates/model/src/orderbook/l2_grid.rs`

当前版本已经不是早期的 `BTreeMap<tick, level>` 原型，而是真正的 chunked sparse-grid。

核心结构：

- 每侧一个 `SideGrid`
- `SideGrid` 内部：
  - `pages: BTreeMap<PageId, GridPage>`
  - `best_page: Option<PageId>`
  - `best_tick: Option<PriceRaw>`
- 每个 `GridPage`：
  - `levels: [Option<GridLevel>; 64]`
  - `occupancy_bitmap: u64`
  - `active_count`

关键映射：

- `tick = price.raw`
- `page_id = tick.div_euclid(64)`
- `slot = tick.rem_euclid(64)`

设计特点：

- 树结构只保留在 page 级别，不再保留在每个 price level 级别
- page 内 level 命中是固定槽位寻址
- page 内 best level 和 top-N 遍历都通过 bitmap scan 完成
- 每侧显式维护 `best_page + best_tick`
- 空 page 会立即回收

工程评价：

- 这是三者中结构设计最激进的一版
- 它试图把“有序 price level 集合”改造成“有序稀疏 page + 页内位图”
- 理论目标是减少 per-level tree overhead，并提升页内访问局部性

当前结论：

- 在结构上，它已经满足“真正 grid 化”的要求
- 但按当前实现和数据集，它还没有在真实 replay 中跑赢 `L2TreeBook`
- 同时，它的内存占用目前明显偏高

## Latest Authoritative Results

当前只保留了最新、最完整的一套对比结果：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000`

摘要文件：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`

实验配置：

- dataset: `binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit: `10_000_000` deltas
- repeats: `3`
- workloads:
  - `replay_only`
  - `replay_periodic_query(q=100)`
  - `replay_periodic_query(q=1000)`

### Replay Throughput

| Workload | baseline updates/s | l2tree updates/s | l2vec updates/s | l2grid updates/s |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 187590.01 | 241336.87 | 126391.43 | 182042.22 |
| `replay_periodic_query::q100` | 186151.56 | 237071.93 | 127102.13 | 181103.72 |
| `replay_periodic_query::q1000` | 187379.40 | 239531.16 | 127536.53 | 182292.63 |

### Peak RSS

| Workload | baseline (MB) | l2tree (MB) | l2vec (MB) | l2grid (MB) |
| --- | ---: | ---: | ---: | ---: |
| `replay_only` | 51.07 | 31.53 | 31.14 | 248.86 |
| `replay_periodic_query::q100` | 51.08 | 31.51 | 31.14 | 248.97 |
| `replay_periodic_query::q1000` | 51.06 | 31.54 | 31.24 | 248.73 |

### Criterion Means

| Case | baseline (ns) | l2tree (ns) | l2vec (ns) | l2grid (ns) |
| --- | ---: | ---: | ---: | ---: |
| `update_existing_level` | 77.215 | 17.472 | 28.450 | 31.366 |
| `insert_new_level` | 261.086 | 73.719 | 59.239 | 463.419 |
| `delete_existing_level` | 206.198 | 79.425 | 69.049 | 300.707 |
| `best_bid_ask` | 19.448 | 16.535 | 10.473 | 45.533 |
| `top_10_query` | 106.096 | 75.924 | 18.465 | 96.162 |

## Engineering Interpretation

结合当前代码和这套结果，现阶段最可靠的判断是：

### 1. `L2TreeBook` 是当前综合最优解

原因不是它最“前沿”，而是它刚好落在一个很好的工程平衡点：

- 比 baseline 明显更轻
- 比 `L2VecBook` 更能承受动态插删
- 比当前 `L2GridBook` 更成熟、更便宜、更稳定

换句话说，`L2TreeBook` 目前不是理论上最特殊的结构，但它是现实里最成功的结构。

### 2. `L2VecBook` 证明了“查询局部性强”不等于“真实回放更快”

它在 `best_bid_ask` 和 `top_10_query` 上确实漂亮，但 replay 不是纯查询工作负载。

在真实增量流下：

- insertion into sorted vec
- removal from sorted vec
- middle shifts

这些成本足以盖过 query 优势。

因此，`L2VecBook` 更像是一个重要的反例：它告诉我们，不能只看静态查询 microbenchmark。

### 3. `L2GridBook` 证明了“结构更专门化”也不必然带来更好结果

当前 `L2GridBook` 已经完成了真正 grid 化，但结果仍然不理想：

- replay 吞吐未超过 `L2TreeBook`
- insert/delete microbench 明显偏慢
- peak RSS 显著偏高

这说明“page + bitmap + best pointer”这条路线还没有被当前实现充分兑现。问题大概率不在接口层，而在以下工程细节：

- `PAGE_SIZE = 64` 是否合适
- 当前 `GridPage` 对象是否过重
- 稀疏分布下 page 密度是否偏低
- `BTreeMap<PageId, GridPage>` 的跨页访问收益是否抵消了 page 本体开销

这部分是基于代码和结果的工程推断，不是代码中直接给出的结论。

## Correctness Status

当前这三种实验实现都已经接入统一验证链路：

- model-level parity / unit tests
- criterion benchmark
- Tardis replay parity
- replay runner 切换

其中 `L2GridBook` 当前版本已经通过：

- `cargo test -p nautilus-model l2_grid --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `source .venv/bin/activate && LD_LIBRARY_PATH=... cargo test -p nautilus-tardis --test l2_book_parity`

因此，现在讨论的重点已经不是“是否正确”，而是“是否值得作为更优结构继续推进”。

## Thesis-Worthy Takeaways

如果从论文写作角度压缩成几条结论，当前最值得保留的是：

1. 针对 `L2_MBP` 做结构特化是有效的，因为 `L2TreeBook` 明显优于通用 baseline。
2. 只优化连续内存和只读查询，并不足以保证真实市场回放性能更优，`L2VecBook` 是反例。
3. 更激进的数据结构专门化需要非常小心地处理对象粒度、稀疏度和缓存局部性，否则会出现 `L2GridBook` 这种“设计更专门，但结果不更好”的情况。
4. 在当前实现阶段，`L2TreeBook` 是最强的工程基线，`L2GridBook` 更适合作为后续优化方向，而不是当前结论性的赢家。

## Current Bottom Line

截至 2026-04-09，针对 `L2_MBP` 的三条工程路线可以总结为：

- `L2TreeBook`: 当前最成功，性能和复杂度平衡最好
- `L2VecBook`: 查询优秀，但动态更新代价过大
- `L2GridBook`: 结构上最有研究价值，但当前实现尚未兑现性能承诺

因此，如果今天要在仓库里选一个“最值得作为当前工作成果代表”的 L2 专用结构，答案是：

- `L2TreeBook`

如果要选一个“最值得继续研究、但尚未完成验证闭环”的方向，答案是：

- `L2GridBook`
