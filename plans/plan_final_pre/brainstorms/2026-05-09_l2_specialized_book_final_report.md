# L2 Specialized Book Final Report Draft

Date: 2026-05-09

## 报告定位

这份报告整理 L2_MBP 特化 order book 的三类结构：`L2TreeBook`、`L2VecBook`、`L2GridBook`。重点回答三个问题：

- 每种结构相对 native `OrderBook(BookType::L2_MBP)` 做了哪些特殊改动。
- 每个改动想获得什么收益，理论上对应什么时间/空间复杂度变化。
- 最终 benchmark 和 replay 结果说明了什么，答辩 slide 应该如何表述。

实验口径来自：

- 代码：`crates/model/src/orderbook/l2.rs`, `l2_vec.rs`, `l2_grid.rs`。
- Runner：`crates/adapters/tardis/bin/l2_baseline.rs`。
- Microbench：`crates/model/benches/l2_book_baseline_criterion.rs`。
- 最终结果：`cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/summaries/comparison_summary.md`。

## Baseline: native OrderBook(L2_MBP)

native `OrderBook` 是通用订单簿，支持 L1_MBP、L2_MBP、L3_MBO。L2_MBP 在 baseline 中仍复用订单级抽象：

- 每侧是 `BookLadder`。
- `BookLadder.levels` 是 `BTreeMap<BookPrice, BookLevel>`。
- `BookLadder.cache` 是 `HashMap<OrderId, BookPrice>`。
- `BookLevel.orders` 是 `IndexMap<OrderId, BookOrder>`。
- L2_MBP 的 price level 会通过 `pre_process_order` 转成合成 `order_id`，再走 add/update/delete order 语义。

baseline 的优点是功能完整、语义统一、L1/L2/L3 共用一套 API。它的代价是 L2 场景只需要 price -> size，却仍然维护 order id cache、BookLevel、IndexMap 和 BookOrder 对象。

理论复杂度上，baseline 的 price-level 更新通常是：

- 定位 price level：`O(log L)`，`L` 是一侧 price level 数。
- order id cache 查找/维护：平均 `O(1)`。
- level 内订单更新：平均 `O(1)`，但要维护 `IndexMap<OrderId, BookOrder>`。
- 空间：`O(L + O)`，`O` 是订单对象数量；L2_MBP 中虽然每个 price level 常近似一个合成 order，但仍保留订单级容器和 cache。

这些 overhead 是三种特化结构共同想消掉或换掉的部分。

## L2TreeBook

### 核心改动

`L2TreeBook` 把 L2_MBP 简化成真正的价格档位树：

- 每侧直接存 `BTreeMap<BookPrice, Quantity>`。
- price level 的 key 仍使用 `BookPrice`，保留 bid 降序、ask 升序的排序语义。
- value 只存聚合后的 `Quantity`。
- Add/Update 都被解释成 price level upsert。
- Delete 直接按 side + price 删除整档。
- Clear 清空双侧 map。
- 不再维护 `HashMap<OrderId, BookPrice>`。
- 不再维护 `BookLevel.orders: IndexMap<OrderId, BookOrder>`。
- 不再在 hot path 构造/更新合成 order id 对应的 order-level 容器。

### 改动收益

| 改动 | 目标收益 | 理论分析 |
| --- | --- | --- |
| `BTreeMap<BookPrice, BookLevel>` -> `BTreeMap<BookPrice, Quantity>` | 减少对象层级和内存占用 | 仍是 `O(log L)` 查找/插入/删除，但常数项更低，空间从 price level + order container 降为 price level + quantity |
| 移除 order id cache | 减少 update/delete 的 hash 查找和一致性维护 | baseline 需要平均 `O(1)` cache 操作；tree book 不需要，逻辑更短 |
| Add/Update 合并为 upsert level | 符合 L2_MBP 的价格档位语义 | 对 missing update 可直接插入，避免 generic order 语义分支 |
| best level 取 `BTreeMap.iter().next()` | 保留 baseline 的有序树优势 | best 查询 `O(1)` amortized / 极低常数 |
| top N 遍历 BTreeMap 前 N 项 | 直接输出 price-size | `O(N)`，少了 BookLevel/BookOrder 聚合 |

### 最终结果

Criterion mean point estimate：

| Case | baseline ns | l2tree ns | 结果 |
| --- | ---: | ---: | --- |
| update existing level | 75.43 | 18.57 | 显著更快 |
| insert new level | 262.52 | 74.57 | 显著更快 |
| delete existing level | 211.58 | 81.30 | 显著更快 |
| best bid/ask | 20.29 | 17.88 | 小幅更快 |
| top 10 query | 109.09 | 77.70 | 更快 |

10M Tardis replay：

| Workload | baseline updates/s | l2tree updates/s |
| --- | ---: | ---: |
| replay only | 186,535.20 | 239,499.86 |
| replay + q100 | 184,806.10 | 235,823.59 |
| replay + q1000 | 185,140.38 | 237,262.84 |

Peak RSS 从 baseline 约 52.1 MB 降到 l2tree 约 32.5 MB。

### 结论

`L2TreeBook` 是当前最适合作为默认工程替代的结构。它没有改变 baseline 的有序树大方向，而是去掉 L2 不需要的订单级抽象，因此真实 replay、microbench 和内存都稳定改善。答辩中建议把它定义为“面向 L2_MBP 语义收窄后的工程主方案”。

## L2VecBook

### 核心改动

`L2VecBook` 把每侧 price levels 放在连续数组中：

- 每侧是排序后的 `Vec<VecLevel>`。
- `VecLevel` 只保留 `price_raw` 和 `size_raw`。
- book 级别保存 `price_precision` 和 `size_precision`，按需重建 `Price` / `Quantity`。
- bid side 按价格降序，ask side 按价格升序。
- 查找用 binary search。
- update existing 是定位后原地改 size。
- insert/delete 会在 Vec 中间移动元素。
- top N 和 checksum 是连续内存前缀扫描。

后续 payload compaction 把单 level payload 从约 64 bytes 压到约 32 bytes。诊断显示 level shift 数量不变，但 shifted bytes 减半。

### 改动收益

| 改动 | 目标收益 | 理论分析 |
| --- | --- | --- |
| BTreeMap 节点 -> 连续 Vec | 提高 cache locality | top N 扫描是连续内存 `O(N)`，CPU cache 友好 |
| `Price`/`Quantity` 对象 -> raw payload | 降低单 level 空间 | level size 约减半；整体空间 `O(L)` 且常数很低 |
| binary search 定位 | 保持有序数组查找效率 | 查找 `O(log L)` |
| 原地 update existing | 降低常见 size update 成本 | existing update `O(log L)` 查找 + `O(1)` 改写 |
| top N 前缀扫描 | 强化 factor/query 场景 | `O(N)`，但常数明显低于树节点遍历 |
| insert/delete 中间移动 | 接受维护成本换查询性能 | 插入/删除 `O(log L + M)`，`M` 是移动元素数量；真实行情中 middle shift 会成为瓶颈 |

### 最终结果

Criterion mean point estimate：

| Case | baseline ns | l2vec ns | 结果 |
| --- | ---: | ---: | --- |
| update existing level | 75.43 | 25.80 | 更快 |
| insert new level | 262.52 | 62.79 | 更快 |
| delete existing level | 211.58 | 66.40 | 更快 |
| best bid/ask | 20.29 | 32.82 | 更慢 |
| top 10 query | 109.09 | 18.25 | 显著最快 |

10M Tardis replay：

| Workload | baseline updates/s | l2vec updates/s |
| --- | ---: | ---: |
| replay only | 186,535.20 | 175,552.72 |
| replay + q100 | 184,806.10 | 174,228.36 |
| replay + q1000 | 185,140.38 | 175,013.03 |

Replay 中 l2vec 低于 baseline 和 l2tree，原因不是查询慢，而是真实稀疏行情存在大量中间 insert/delete，Vec shift 成本抵消了连续内存收益。

查询延迟非常强：

| Workload | baseline avg query ns | l2vec avg query ns |
| --- | ---: | ---: |
| q100 | 3,379 | 757 |
| q1000 | 5,354 | 1,299 |

Peak RSS 约 30.6 MB，是四者中最低。

### 结论

`L2VecBook` 不是最好的实时 book maintenance 默认结构，但非常适合连续深度扫描、top-k feature、因子计算或离线 analytics。答辩中建议表述为“查询友好、内存紧凑，但维护路径受中间位移影响的结构”。

## L2GridBook

### 核心改动

`L2GridBook` 把价格 raw tick 映射到稀疏分页网格：

- tick = `price.raw`。
- 每页固定 64 个 slot。
- `SideGrid.pages` 是 `BTreeMap<PageId, GridPage>`。
- `GridPage` 内部是 `[Option<GridLevel>; 64]`。
- `occupancy_bitmap: u64` 标记哪些 slot 有 level。
- `active_count` 记录有效 slot 数。
- 每侧维护 `best_page` / `best_tick` cache。
- 删除 best 后先修复页内 best，再必要时跨 page 查找。
- `GridLevel` 压缩后只保存 size 和 price_precision，不保存完整 Price。
- page id 和 slot 使用 Euclidean division，支持负 tick。

### 改动收益

| 改动 | 目标收益 | 理论分析 |
| --- | --- | --- |
| price tree -> tick page grid | 利用交易价格 tick 离散性 | 定位 page `O(log P)`，slot 访问 `O(1)`，P 是 active page 数 |
| page 内 64 slot + bitmap | 提升 dense/deep 场景扫描效率 | 页内 best 和 occupied slot 扫描用位运算，常数低 |
| best_page / best_tick cache | 降低 best 查询成本 | 非删除 best 的 update 后 best 查询 `O(1)` |
| 删除 best 局部修复 | 避免每次全局查找 | 页内还有 level 时 `O(1)` 级修复；空页时跨 page `O(log P)` |
| 压缩 GridLevel payload | 降低 page 内存 | 单 page 从约 5152 bytes 降到约 4128 bytes，但仍按 page 预留 slot |

### 理论优势和约束

Grid 的优势条件非常明确：

- 价格分布 dense，active slots / allocated slots 比例高。
- 查询深度大，top N 经常跨许多连续价位。
- 更新集中在已有 page 内，减少 page 分配和 BTree page 查询。

Grid 的劣势也很明确：

- 真实 BTCUSDT L2 在一天内价格跨度大、活跃档位相对稀疏。
- 每个 active page 固定带 64 slot，稀疏时空间浪费明显。
- page 之间仍用 BTreeMap 管理，无法完全消除树操作。
- 如果查询深度浅，bitmap/page 的额外逻辑未必比简单树遍历便宜。

### 最终结果

Criterion mean point estimate：

| Case | baseline ns | l2grid ns | 结果 |
| --- | ---: | ---: | --- |
| update existing level | 75.43 | 33.90 | 更快 |
| insert new level | 262.52 | 362.33 | 更慢 |
| delete existing level | 211.58 | 244.80 | 更慢 |
| best bid/ask | 20.29 | 57.51 | 更慢 |
| top 10 query | 109.09 | 208.06 | 更慢 |

10M Tardis replay：

| Workload | baseline updates/s | l2grid updates/s |
| --- | ---: | ---: |
| replay only | 186,535.20 | 190,025.20 |
| replay + q100 | 184,806.10 | 189,194.93 |
| replay + q1000 | 185,140.38 | 187,935.21 |

Grid replay throughput 略高于 baseline，但远低于 l2tree。查询平均延迟更高：

| Workload | baseline avg query ns | l2grid avg query ns |
| --- | ---: | ---: |
| q100 | 3,379 | 4,554 |
| q1000 | 5,354 | 6,249 |

Peak RSS 约 206 MB，明显高于 baseline 的约 52 MB 和 l2tree/l2vec 的约 30-33 MB。

### 结论

`L2GridBook` 不是通用默认替代。它验证了 tick-grid 思路在 dense/deep 条件下有潜力，但真实 sparse replay 的空间放大和浅查询成本使它不适合作为默认 book。答辩中建议表述为“条件型结构：适合高密度深度簿，不适合当前 BTCUSDT 稀疏 replay 的通用路径”。

## 横向总结

| Structure | 主要优化方向 | 维护复杂度 | 查询复杂度 | 空间 | 最终定位 |
| --- | --- | --- | --- | --- | --- |
| baseline | 通用 L1/L2/L3 订单语义 | `O(log L)` + order/cache 常数 | best 低成本，topN `O(N)` | `O(L + O)` | oracle 和默认安全路径 |
| L2TreeBook | L2 price-level tree | `O(log L)`，低常数 | best 低成本，topN `O(N)` | `O(L)` | 默认工程候选 |
| L2VecBook | 连续数组 + raw payload | update `O(log L)`，insert/delete `O(log L + shift)` | topN `O(N)` 且 cache 友好 | `O(L)`，最低常数 | factor/top-k 查询结构 |
| L2GridBook | tick-indexed sparse page | `O(log P + 1)` | dense/deep 时接近 `O(N)` 低常数 | `O(P * page_size)` | dense/deep 条件型结构 |

综合 10M replay：

| Book | replay only updates/s | q100 avg query ns | q1000 avg query ns | peak RSS |
| --- | ---: | ---: | ---: | ---: |
| baseline | 186,535.20 | 3,379 | 5,354 | ~52.1 MB |
| l2tree | 239,499.86 | 2,139 | 2,605 | ~32.5 MB |
| l2vec | 175,552.72 | 757 | 1,299 | ~30.6 MB |
| l2grid | 190,025.20 | 4,554 | 6,249 | ~206 MB |

## 可用于答辩 slide 的核心表述

建议主线：

1. Baseline 不是低质量实现，而是通用实现；它的成本来自 L2 场景复用订单级抽象。
2. `L2TreeBook` 证明“按 L2 语义收窄”可以稳定拿到真实 replay 收益：吞吐约 +28.4%，内存约 -37%，同时保持有序树的鲁棒性。
3. `L2VecBook` 证明连续内存对 top-k / factor 查询非常有效：q100/q1000 查询延迟显著降低，但真实维护受中间 shift 影响，不适合作为默认实时维护结构。
4. `L2GridBook` 证明 tick-grid 是条件型优化：dense/deep 负载可能有优势，但真实稀疏行情中 page 空间放大明显，因此不应作为通用默认。
5. 最终工程结论不是“一种结构绝对最快”，而是按场景选择：tree 做主路径，vec 做 factor/query 辅助，grid 做 dense/deep 研究候选。

## 不建议在答辩中使用的表述

- 不要说 “baseline 很差”。更准确的说法是 “baseline 是通用订单簿，L2 场景存在可消除的订单级抽象开销”。
- 不要说 “L2VecBook 失败”。它在查询和内存上表现最好，只是不适合当前真实 replay 的维护主路径。
- 不要说 “L2GridBook 失败”。它是条件型结构，真实稀疏数据不是它的主场。
- 不要说 “L2TreeBook 永远最快”。它是当前 workload 下综合最优，不代表所有密度、深度、查询比例都最优。

## 最终结论

论文和答辩可以把三种结构解释为一组递进实验：

- `L2TreeBook`：去掉订单级冗余，得到稳定工程收益，是最终推荐主方案。
- `L2VecBook`：把 levels 放进连续内存，证明 top-k 查询和因子计算可以极快，但维护成本受真实行情结构限制。
- `L2GridBook`：把价格离散性进一步编码进 page/grid，证明结构优化需要匹配数据密度，否则空间和常数会反噬。

这组结果支撑的最终观点是：低延迟 L2 order book 优化不能只看 Big-O，也必须看数据分布、查询深度、更新/查询比例和内存布局。当前最稳健的生产化方向是 `L2TreeBook`，同时保留 `L2VecBook` 和 `L2GridBook` 作为特定负载下的扩展候选。
