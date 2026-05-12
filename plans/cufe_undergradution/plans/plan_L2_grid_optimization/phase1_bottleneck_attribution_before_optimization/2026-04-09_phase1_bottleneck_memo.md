# Phase 1 Bottleneck Memo

Date: 2026-04-09

## Goal

phase1 的目标不是先优化，而是先把这四个问题用证据回答清楚：

1. 当前 `L2GridBook` 的主内存来源是什么。
2. 当前 replay-time 的主性能来源是什么。
3. 哪些 slowdown 是结构性的，哪些还像实现细节。
4. 哪些优化方向值得进入后续 phase，哪些应该尽早放弃。

## Inputs

本 memo 基于四类输入：

- frozen baseline comparison
  - `all_books_summary.md`
  - `criterion_summary.json`
  - `runner_summary.json`
- 当前实现
  - `crates/model/src/orderbook/l2_grid.rs`
  - `crates/model/src/orderbook/l2.rs`
  - `crates/model/src/orderbook/l2_vec.rs`
- phase1 诊断原始输出
  - `2026-04-09_phase1_diagnostics_report.json`
- phase0 handoff
  - `2026-04-09_phase0_measurement_handoff.md`

## Executive Conclusion

phase1 的结论已经足够明确：

当前 `L2GridBook` 的主要问题不是“还差一点微优化”，而是当前 authoritative replay 下 page occupancy 完全退化成了 `1 page = 1 level`。在这个前提下，`GridPage` 的固定 64 槽表示会把每个活跃价位包装成一个约 `5 KB` 的 page body，再叠加 page-level `BTreeMap` 索引开销，于是：

- RSS 异常高
- insert / delete / best repair 的常数明显放大
- `grid` 理论上的 page-local density 优势完全没有兑现

换句话说，当前 `L2GridBook` 的主要矛盾是结构和 workload 的错配，而不是单个函数还没抠干净。

## Finding 1: Dominant Memory Source

### Evidence

phase1 诊断测得：

- `GridLevel = 64 bytes`
- `Option<GridLevel> = 80 bytes`
- `GridPage = 5,152 bytes`
- 其中 `levels: [Option<GridLevel>; 64]` 独占 `5,120 bytes`
- page metadata 只占 `32 bytes`

同时 authoritative replay 采样显示：

- bids 的 `avg active slots / populated page = 1.0`
- asks 的 `avg active slots / populated page = 1.0`
- bid / ask 两侧 `p50 / p95 / max active slots / page` 全部等于 `1`

### Interpretation

所以当前内存 blow-up 的第一主因不是：

- bitmap
- `active_count`
- `best_page` / `best_tick`

而是：

- 固定 page body 太重
- 且 replay 下几乎永远只被一个活跃档位使用

只算 page body，不算 page index node 和 allocator：

- `1 active slot / page -> 5,152 bytes / active level`

这与 frozen baseline 中的 RSS 对比完全一致：

- `l2grid ~248.9 MB`
- `l2tree ~31.5 MB`
- `l2vec ~31.1 MB`

## Finding 2: Dominant Replay-Time Performance Source

### Existing authoritative microbench signal

frozen criterion summary 已经把热点暴露得很清楚：

| Case | `l2tree` ns | `l2grid` ns | signal |
| --- | ---: | ---: | --- |
| `update_existing_level` | `17.47` | `31.37` | `l2grid` 不差，但没赢 |
| `insert_new_level` | `73.72` | `463.42` | `l2grid` 明显最弱 |
| `delete_existing_level` | `79.42` | `300.71` | `l2grid` 明显最弱 |
| `best_bid_ask` | `16.54` | `45.53` | `l2grid` 明显更慢 |
| `top_10_query` | `75.92` | `96.16` | `l2grid` 略弱于 `l2tree` |

### Structural explanation

这组数据和 occupancy 证据可以拼起来看：

1. `insert_new_level`
   - 当前 replay 下新增一个 level，基本等价于新增一个 page
   - 意味着 `BTreeMap<PageId, GridPage>` 也几乎在按 level 粒度扩张
   - 这直接解释了为什么 insert 比 `L2TreeBook` 还慢很多

2. `delete_existing_level`
   - 当前 replay 下删除一个 level，也经常等价于删除整个 page
   - 于是删除不仅要改 slot，还要 page reclaim、tree remove、可能再 repair best

3. `best_bid_ask`
   - 理论上 cached best 应该很便宜
   - 但当 page 退化成“一页一档”后，best cache 的存在并没有换来 page-local density
   - delete-best 之后的恢复路径也更像在 page tree 上跳页，而不是在局部稠密 page 内复用 bitmap

4. `top_n`
   - 当前 `top_10_query` 没有崩，说明遍历路径并不是唯一问题
   - 真正的问题更偏向 update path，尤其是 insert / delete / best repair

## Finding 3: Structural vs Implementation-Specific

### Structural problems

这几项已经可以视为结构性问题：

1. 当前 authoritative replay 下，page occupancy 稳定退化成 `1`
2. `BTreeMap<PageId, GridPage>` 几乎退化成“每个活跃价位一个 page 索引节点”
3. `PAGE_SIZE = 64` 的固定数组表示在这个 workload 上几乎只制造放大，不制造局部性
4. delete-best repair 的复杂度和常数无法被页内密度抵消

### Implementation-specific problems

这几项仍然像实现细节，后续可以继续量化：

1. slot 内保存完整 `Price`
   - 当前 `Price = 32 bytes`
   - 每个 `GridLevel` 都背一份 `Price + Quantity`
   - 这会把 `Option<GridLevel>` 推高到 `80 bytes`

2. `Option<GridLevel>` 表示过重
   - 即便不改 page 结构，只压缩 slot payload 也可能显著降低 page body

3. `best_bid_ask` 常数仍偏高
   - 说明 best 路径本身也有实现成本
   - 但它现在不是第一优先级，因为主矛盾仍然是 occupancy 崩成 `1`

## Finding 4: Deep Query Hypothesis Is Not Dead, But It Is Not Proven

phase1 新增了一个支持性 query probe：

- 每侧 `1024` levels
- depth：`10 / 100 / 500 / 1000`
- 通过 `cargo run` 的 dev build 跑

它不是新的 authoritative benchmark，但可以用来看趋势：

| Book | `top_10` ns | `top_100` ns | `top_500` ns | `top_1000` ns |
| --- | ---: | ---: | ---: | ---: |
| `l2tree` | `1444` | `13932` | `69639` | `138968` |
| `l2vec` | `283` | `2323` | `11436` | `22885` |
| `l2grid` | `1247` | `12155` | `61750` | `136711` |

这组趋势说明两点：

1. `L2GridBook` 的深度 query slope 并不差，至少没有随着 depth 增长而比 `L2TreeBook` 更快恶化。
2. 但这还不能推翻 phase1 的核心结论，因为 authoritative replay 的真实问题不是 deep query，而是 sparse pages + update path。

所以现在更准确的表述是：

- “grid 在深 query synthetic probe 下没有显示出明显劣势”
- 但还不能说“grid 已经找到真实 workload 优势”

## Root-Cause Ranking

### Rank 1

`fixed GridPage footprint under occupancy ~= 1`

- expected upside：`very high`
- implementation risk：`high`
- validation cost：`medium`
- judgement：这是当前 RSS 和 replay-time 常数的第一主因

### Rank 2

`page-level BTreeMap degenerating toward one node per active level`

- expected upside：`high`
- implementation risk：`medium`
- validation cost：`medium`
- judgement：它本身不是唯一问题，但和 Rank 1 强耦合

### Rank 3

`storing full Price inside each occupied slot`

- expected upside：`medium`
- implementation risk：`medium`
- validation cost：`low`
- judgement：值得保留，但单独做不够

### Rank 4

`best repair / best query constant cost`

- expected upside：`low to medium`
- implementation risk：`low`
- validation cost：`low`
- judgement：可做，但不能当主战场

### Rank 5

`PAGE_SIZE = 64`

- expected upside：`unknown`
- implementation risk：`low`
- validation cost：`low`
- judgement：可以做 sweep，但在 phase1 证据下它不是第一顺位

## What Phase 1 Rules Out

phase1 已经足够排除下面这些错误方向：

1. 不能再把当前问题理解成“grid 只差一点 cache-friendly 微调”。
2. 不能再把 RSS 异常归因给 bitmap 或少量 side metadata。
3. 不能把当前 workload 下的失败简单理解成“query 不够深”，因为 update path 的结构成本已经先炸出来了。
4. 不能只靠 `PAGE_SIZE` 小调参就期望把 `248 MB` 拉回到 `31 MB` 量级。

## Phase 1 Exit Decision

phase1 的退出条件已经满足：

- memory accounting：有
- occupancy / sparsity evidence：有
- operation-path evidence：有
- root-cause ranking：有

同时，phase1 也没有触发“彻底终止任务”的 early-stop：

- 它没有证明 `grid` 路线必死
- 但它已经证明：如果不先面对 sparse-page mismatch，后续优化很容易只是在错误抽象上继续抠常数

## Recommended Handoff

phase1 结束后的推荐动作是：

1. Phase 2 先做最小 workload matrix
   - 明确构造 dense contiguous pages / deep-query-heavy workload
   - 验证 `grid` 的理论主场是否真的存在

2. Phase 3 若继续优化，优先级应改成：
   - 先处理 sparse-page representation / slot payload 压缩
   - 再考虑 `PAGE_SIZE` sweep
   - 最后才是 best/delete 微调

如果跳过上面这一步，直接进入“继续优化当前 64-slot sparse page 实现”，高概率会继续得到：

- 小幅常数改进
- 但结构性 RSS 和 insert/delete 劣势仍然存在
