# Phase 3 Refresh Summary

日期：2026-03-24

## 结论

新的 chunked sparse-grid `L2GridBook` 已经完成实现、correctness 验证和统一 workload 测量，但当前结果不支持它优于 `L2TreeBook`。

这不是无效结果。相反，它清楚地表明：

- 非树型 grid 路线并不会自动更快
- chunked sparse page 在当前 L2 数据分布下会引入显著的 page 管理开销
- 如果页面局部密度不足，内存放大和插删常数会抵消 tick-indexed 设计的潜在收益

## 本轮验证范围

- `cargo test -p nautilus-model l2_grid --lib`
- `cargo test -p nautilus-tardis --test l2_book_parity`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `cargo check -p nautilus-tardis --bin tardis-l2-baseline`
- workload 配置与 Phase 1 保持一致：
  - 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
  - 子集规模：前 `10,000,000` 条 delta
  - repeats：`3`
  - depth：`10`
  - workload：`replay_only`、`q=100`、`q=1000`

刷新结果目录：

- `cufe_undergraduate_playground/results/comparisons/l2grid_subset_10m_r3_q100_q1000_refresh/`

统一四方结果目录：

- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/`

## 关键结果

### Replay workload

- `replay_only`
  - `baseline`: `187.59k updates/s`
  - `l2tree`: `241.34k updates/s`
  - `l2vec`: `126.39k updates/s`
  - `l2grid`: `182.04k updates/s`

- `replay_periodic_query_q100`
  - `baseline`: `186.15k updates/s`
  - `l2tree`: `237.07k updates/s`
  - `l2vec`: `127.10k updates/s`
  - `l2grid`: `181.10k updates/s`

- `replay_periodic_query_q1000`
  - `baseline`: `187.38k updates/s`
  - `l2tree`: `239.53k updates/s`
  - `l2vec`: `127.54k updates/s`
  - `l2grid`: `182.29k updates/s`

### Peak RSS

- `baseline`: 约 `51 MB`
- `l2tree`: 约 `31.5 MB`
- `l2vec`: 约 `31.2 MB`
- `l2grid`: 约 `249 MB`

### Microbench

- `update_existing_level`: `31.37 ns`
- `insert_new_level`: `463.42 ns`
- `delete_existing_level`: `300.71 ns`
- `best_bid_ask`: `45.53 ns`
- `top_10_query`: `96.16 ns`

## 如何解释这组结果

`L2GridBook` 当前的主要问题不是 correctness，而是局部稠密性假设没有成立得足够好。

当前实现将每个活跃 page 扩展成固定 `64` 槽位数组，并为其维护 bitmap。这样做虽然减少了 per-level tree node，但也带来了新的成本：

- page 级稀疏浪费
- page 分配与回收成本
- delete-best 修复与跨页回退复杂度
- 插入与删除路径上的更大常数

结果就是：

- 理论上更“纯 grid”
- 但实际 replay 吞吐退回到接近 baseline
- 内存显著放大，明显差于 `L2TreeBook`

## 当前最稳的研究结论

- `L2TreeBook` 仍然是当前最强、最稳的主实现
- `L2VecBook` 继续证明 “query locality 强，但 replay 不适合作为主结构”
- `L2GridBook` 则提供了一个很有价值的负例：真正的非树型 grid 需要更强的局部密度假设和更细的 page/index 设计，否则收益会被 page sparsity 吞掉

## 下一步建议

- 调整 `PAGE_SIZE`
- 评估 page index 从 `BTreeMap<PageId, GridPage>` 到更轻索引结构的收益
- 研究 page pooling / slab reuse
- 评估更激进的 page-level bitmap 与 next-page hint
- 在论文和中期汇报里如实把 `L2GridBook` 表述为“揭示真实 trade-off 的探索性实现”，而不是当前最佳方案
