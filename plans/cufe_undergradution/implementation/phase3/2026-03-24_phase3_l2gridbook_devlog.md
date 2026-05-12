# Phase 3 Devlog / Implementation Note: `L2GridBook`

Date: 2026-03-24

## Goal

将 `crates/model/src/orderbook/l2_grid.rs` 从“按 price level 直接挂
`BTreeMap<tick, level>`”的原型，推进成真正的 chunked sparse-grid：

- 稀疏 page 索引
- 固定大小 page 槽位
- bitmap 驱动的页内活跃 level 跟踪
- 显式 best bid / ask page/tick 缓存

目标不是改 `L2BookOps`，而是在保持 replay / parity / bench 接口不变的前提下，
减少 `L2TreeBook` 剩余的 per-level tree overhead。

## Changed Files

- `crates/model/src/orderbook/l2_grid.rs`
- `crates/adapters/tardis/tests/l2_book_parity.rs`

## Final Layout

`L2GridBook` 现在按 side 拆成两个 `SideGrid`。

每个 `SideGrid` 包含：

- `pages: BTreeMap<PageId, GridPage>`
- `best_page: Option<PageId>`
- `best_tick: Option<PriceRaw>`

其中：

- `PageId = floor_div(price.raw, PAGE_SIZE)`
- `PAGE_SIZE = 64`
- `slot = mod_floor(price.raw, PAGE_SIZE)`

每个 `GridPage` 包含：

- `base_tick`
- `levels: [Option<GridLevel>; 64]`
- `occupancy_bitmap: u64`
- `active_count`

`GridLevel` 保存：

- `price: Price`
- `size: Quantity`

因此现在的树结构只保留在 page 级别，不再是每个 price level 一个 tree node。

## Key Design Decisions

### 1. Price -> (page, slot) 映射

映射规则为：

- `tick = price.raw`
- `page_id = tick.div_euclid(PAGE_SIZE)`
- `slot = tick.rem_euclid(PAGE_SIZE)`

这里使用 Euclidean 除法，而不是普通 `/` 和 `%`，原因是要保证负数 raw 价格也稳定：

- `-1 -> (page=-1, slot=63)`
- `-64 -> (page=-1, slot=0)`
- `-65 -> (page=-2, slot=63)`

这保证 page/slot 分解在全 raw price 空间上是确定性的。

### 2. Page Container Choice

本阶段采用：

- `BTreeMap<PageId, GridPage>`

而不是：

- `HashMap<PageId, GridPage>`

原因：

- top-N 遍历需要自然的价格顺序
- delete-best 的跨页回退需要稳定地找前一页 / 后一页
- 这样仍然把 tree 比较成本限制在 page 级别，而不是每个 level 级别

这和计划里的主路线一致：先做“ordered sparse page index + fixed-size page arrays + bitmap”。

### 3. Bitmap-Assisted In-Page Scans

每个 page 用一个 `u64` bitmap 表示 64 个 slot 是否活跃。

页内 best level 查找：

- buy: `63 - bitmap.leading_zeros()`
- sell: `bitmap.trailing_zeros()`

页内 top-N 遍历：

- buy 从高 bit 往低 bit 扫
- sell 从低 bit 往高 bit 扫

这样 page 内不需要再做树查找，也不需要线性扫描 64 个槽位。

### 4. Best Bid / Ask Maintenance

每个 side 显式缓存：

- `best_page`
- `best_tick`

维护策略：

- 插入更优 tick 时直接更新缓存
- 更新已有 best tick 时缓存不变
- 删除 best tick 时，先在同页内找下一档
- 如果该页空了，再回退到相邻的下一个非空 page
- 如果 side 全空，则清空 best cache

这比每次 best 查询都去全结构扫描要便宜，也符合本 phase 的目标。

### 5. Empty Page Reclamation

当 page 的最后一个 slot 被删掉时：

- 立即从 `pages` 中移除该 page

这样避免保留空 page，并保证：

- page bitmap 和 slot 存储一致
- `pages` 中的 page 总是非空 page

## Metadata / Semantics Alignment

`sequence` / `ts_last` / `update_count` 更新逻辑继续对齐 `L2TreeBook`：

- out-of-order 输入保留 warning
- `sequence` 取高水位
- `ts_last` 取高水位
- `update_count` 每次 book 操作递增

`NoOrderSide` 语义也继续对齐 baseline / `L2TreeBook`：

- `Add + NoOrderSide` -> error
- `Update/Delete + NoOrderSide + order_id != 0` -> skip
- `Update/Delete + NoOrderSide + order_id == 0` -> error
- `Clear` -> allowed

内部 level 语义保持：

- one level per `(side, price)`
- `Add` / `Update` -> upsert
- `Delete` -> remove exact level
- zero-size upsert -> remove level

## Tests Added / Kept

`l2_grid.rs` 中覆盖了这些关键点：

- canonical `Price::raw` tick conversion
- Euclidean `tick -> (page_id, slot)` conversion
- best delete fallback within the same page
- best delete fallback across pages
- zero-size upsert removes level
- empty page reclamation
- bitmap / slot consistency
- clear behavior
- synthetic baseline parity sequences
- `NoOrderSide` skip parity

`crates/adapters/tardis/tests/l2_book_parity.rs` 继续验证：

- `L2TreeBook` vs baseline
- `L2GridBook` vs baseline

使用同一份小样本 Tardis CSV replay。

## Validation Run

已通过：

- `cargo check -p nautilus-model --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `cargo test -p nautilus-model l2_grid --lib`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo test -p nautilus-tardis --test l2_book_parity`

最后一项仍需要显式设置 `LD_LIBRARY_PATH`，否则运行时会缺：

- `libpython3.13.so.1.0`

## What Improved Relative to the Prototype

相对之前的 per-level `BTreeMap<tick, level>` 原型，这版真正完成了 Phase 3 要求里的结构升级：

- tree node 数量从“每个活跃价位一个”降到“每个活跃 page 一个”
- level 命中后页内访问是固定槽位寻址
- top-N 和 best-page repair 可以利用 bitmap scan
- 空页会立即回收，不会留下稀疏残片

## Remaining Trade-Offs

这版仍然不是终点，当前 trade-off 很明确：

- 全局 page 索引仍是 `BTreeMap`，所以跨页查找仍有树成本
- `PAGE_SIZE = 64` 只是本 phase 的起点，不一定是最终最优
- 如果真实 replay 中活跃价位非常分散，page-local density 可能不高
- delete-best 的逻辑明显比 `L2TreeBook` 更复杂

## Practical Conclusion

现在的 `L2GridBook` 已经满足这个 phase 新计划里的核心标准：

- final implementation no longer uses `BTreeMap<tick, level>` as primary storage
- has sparse ordered page index
- has fixed-size page arrays
- has bitmap-assisted active-level tracking
- preserves `L2BookOps` correctness and integration
- passes unit tests and Tardis replay parity

如果下一步 benchmark 结果仍然不明显优于 `L2TreeBook`，后续优化方向会更偏向：

- page index container tuning
- `PAGE_SIZE` tuning
- hash-index + explicit ordered best-page hints
- 更激进的 page pooling / slab reuse

而不是再退回 per-level tree 方案。

## Post-Refresh Performance Result

在实现完成后，我们按与 Phase 1 完全一致的配置重新跑了共享 workload：

- 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- 子集规模：前 `10,000,000` 条 delta
- repeats：`3`
- workload：`replay_only`、`replay_periodic_query(q=100)`、`replay_periodic_query(q=1000)`

结果目录：

- `cufe_undergraduate_playground/results/comparisons/l2grid_subset_10m_r3_q100_q1000_refresh/`

合并后的四方总表：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/`

这一轮结果说明：

- `L2GridBook` 的 correctness 没有问题
- 但当前 chunked sparse-grid 实现在真实 replay 下并没有超过 `L2TreeBook`
- `replay_only` 吞吐约 `182k updates/s`，已经回落到接近 baseline
- 峰值 RSS 约 `249 MB`，明显高于 baseline 和 `L2TreeBook`

这说明当前 Phase 3 的主要矛盾不再是“能不能做成 grid”，而是：

- page 局部密度是否足够高
- `PAGE_SIZE=64` 是否合理
- sparse page 布局是否引入了过大的内存放大
- delete-best / page repair 带来的额外常数是否抵消了 tick-indexed 的理论收益

因此，这版实现更适合在论文里被表述为：

- 一个成功落地、通过 correctness 的非树型 grid 原型
- 以及一个揭示真实 trade-off 的实验结果

而不是当前最佳实现。
