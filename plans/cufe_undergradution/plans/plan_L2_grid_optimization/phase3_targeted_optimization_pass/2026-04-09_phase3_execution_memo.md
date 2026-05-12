# Phase 3 Execution Memo

Date: 2026-04-09

## 目标

Phase 3 的实际执行目标是：

1. 把 Phase 2 冻结的 canonical workload matrix 变成真实结果。
2. 用这些结果回答 `grid` 的价值边界到底在哪里。
3. 决定后续优化应继续押在哪类 workload 上，而不是在错误舞台上继续抠常数。

## 本阶段完成的工作

### 1. 跑完 real control

已执行：

- `real_shallow_control`

结果目录：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_shallow_control_btcusdt_10m`

### 2. 跑完 real deep-query sparse replay

已执行：

- `depth=500, q=1000`
- `depth=500, q=100`

之所以加跑 `q=100`，是因为 `q=1000` 下四个 book 的 query share 都低于 `10%`，满足了 Phase 2 里写死的扩展触发条件。

结果目录：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_deep_query_sparse_replay_btcusdt_10m/depth500_q1000`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_deep_query_sparse_replay_btcusdt_10m/depth500_q100`

### 3. 新增 synthetic runner

本阶段新增：

- `crates/adapters/tardis/bin/l2_synthetic_matrix.rs`

它支持：

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

实现方式是：

- 用固定 per-side schedule 维持 `update / insert / delete` mix
- 让 bid/ask 两侧各自保持稳定 active depth
- 用 raw tick 直接控制 dense vs sparse page occupancy
- 对 `l2grid` 单独导出 final occupancy summary

### 4. 跑完 dense / sparse synthetic 对照

已执行：

- `synthetic_dense_contiguous_home_court`
- `synthetic_sparse_page_control`

结果目录：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_dense_contiguous_home_court_1024lvl/depth500_q100`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_sparse_page_control_1024lvl/depth500_q100`

## Summary Table

### Real shallow control

| Book | Throughput updates/s | Peak RSS MB |
| --- | ---: | ---: |
| `baseline` | `180,560.68` | `52.13` |
| `l2tree` | `231,061.70` | `32.61` |
| `l2vec` | `123,832.16` | `32.11` |
| `l2grid` | `178,377.40` | `249.97` |

### Real deep-query sparse replay, `depth=500, q=1000`

| Book | Throughput updates/s | Avg query ns | Query share | Peak RSS MB |
| --- | ---: | ---: | ---: | ---: |
| `baseline` | `176,867.88` | `144,957` | `2.56%` | `52.05` |
| `l2tree` | `226,905.45` | `71,084` | `1.61%` | `32.54` |
| `l2vec` | `123,345.11` | `12,658` | `0.16%` | `32.17` |
| `l2grid` | `176,709.44` | `104,474` | `1.85%` | `249.96` |

### Real deep-query sparse replay, `depth=500, q=100`

| Book | Throughput updates/s | Avg query ns | Query share | Peak RSS MB |
| --- | ---: | ---: | ---: | ---: |
| `baseline` | `133,482.52` | `132,088` | `17.63%` | `52.10` |
| `l2tree` | `181,913.70` | `75,957` | `13.82%` | `32.57` |
| `l2vec` | `109,298.79` | `13,587` | `1.49%` | `32.00` |
| `l2grid` | `133,305.51` | `104,170` | `13.89%` | `249.77` |

### Synthetic dense home court, `1024 levels/side, depth=500, q=100`

| Book | Throughput updates/s | Avg query ns | Peak RSS MB |
| --- | ---: | ---: | ---: |
| `baseline` | `277,644.71` | `113,402` | `18.06` |
| `l2tree` | `478,681.44` | `69,790` | `16.83` |
| `l2vec` | `668,282.16` | `11,786` | `16.44` |
| `l2grid` | `600,664.85` | `15,311` | `16.73` |

`l2grid` final occupancy summary:

- bids: `p50 active slots/page = 64`
- asks: `p50 active slots/page = 64`
- bids: `fraction pages >= 32 slots = 0.9412`
- asks: `fraction pages >= 32 slots = 1.0`

### Synthetic sparse control, `1024 levels/side, depth=500, q=100`

| Book | Throughput updates/s | Avg query ns | Peak RSS MB |
| --- | ---: | ---: | ---: |
| `baseline` | `277,177.09` | `113,343` | `18.17` |
| `l2tree` | `479,546.91` | `69,617` | `16.80` |
| `l2vec` | `671,498.14` | `11,728` | `16.64` |
| `l2grid` | `359,989.52` | `65,408` | `31.49` |

`l2grid` final occupancy summary:

- bids: `p50 active slots/page = 1`
- asks: `p50 active slots/page = 1`
- bids: `fraction pages >= 32 slots = 0.0`
- asks: `fraction pages >= 32 slots = 0.0`

## Main Findings

### Finding 1: real shallow control 完整复现了早期结论

`l2tree` 仍是当前真实 replay 下的综合最优方案。

`l2grid` 的 throughput 只和 baseline 接近，但 peak RSS 仍接近 `250 MB`，远高于其他专门结构。

这说明：

- Phase 1 对 sparse replay mismatch 的判断没有被推翻
- 如果 workload 不变，继续硬抠 `grid` 常数大概率不会改变默认工程结论

### Finding 2: deep query alone 在真实 sparse replay 上不能救回 `grid`

这一条现在可以说得更硬一些。

在 `depth=500, q=1000` 下：

- `l2grid` query 明显优于 baseline
- 但仍明显慢于 `l2tree`
- throughput 和 RSS 也没有改善

在 `depth=500, q=100` 下：

- query share 已经上升到 `13%` 以上
- 这意味着 deep query 的权重已经足够真实地影响总体运行时间
- 但 `l2grid` 仍然同时输给 `l2tree` 的 throughput 和 avg query

因此，本阶段可以明确写下：

- 在真实 sparse replay 上，deep query alone 不是 `grid` 的主救命点

### Finding 3: dense synthetic 确实让 `grid` 出现了主场信号

这一组 workload 是 Phase 3 最重要的新信息。

它满足了 Phase 2 定义的 dense validity threshold：

- bid `p50 active slots/page = 64`
- ask `p50 active slots/page = 64`
- bid `fraction pages >= 32 slots = 0.9412`
- ask `fraction pages >= 32 slots = 1.0`

而在这样的 dense pages 下：

- `l2grid` throughput 为 `600,664.85 updates/s`
- `l2tree` throughput 为 `478,681.44 updates/s`
- `l2grid` 对 `l2tree` 有约 `25.5%` 的 throughput 优势

同时：

- `l2grid avg query = 15,311 ns`
- `l2tree avg query = 69,790 ns`
- `l2grid` 的 deep query 比 `l2tree` 快约 `4.6x`

这说明：

- `grid` 并不是“任何情况下都不行”
- 当 page density 真的成立时，它确实能兑现一部分路线优势

### Finding 4: sparse synthetic 把这个信号重新打掉了

sparse control 的目的就是验证 dense signal 是否真的来自 density。

这一组 workload 也满足了 sparse validity threshold：

- bid `p50 active slots/page = 1`
- ask `p50 active slots/page = 1`
- bid `fraction pages >= 32 slots = 0.0`
- ask `fraction pages >= 32 slots = 0.0`

而当 occupancy 退化回 `1` 之后：

- `l2grid` throughput 下降到 `359,989.52 updates/s`
- `l2tree` throughput 仍有 `479,546.91 updates/s`
- `l2grid` 相比 `l2tree` 反而落后约 `24.9%`

这说明：

- dense home-court 上出现的 throughput 翻转，不是偶然噪声
- 至少很大一部分信号，确实是和 page density 绑定的

### Finding 5: `l2vec` 在这个 synthetic 设定里仍然是最强 query/throughput 选手

这一点也要如实写下。

不管 dense 还是 sparse，当前 synthetic 设定里：

- `l2vec` 都有最高 throughput
- `l2vec` 也有最强 query

所以 Phase 3 的结论不应该被写成：

- `grid` 已经成为全局最佳结构

更准确的表述是：

- `grid` 的价值边界被确认了
- 但它还没有成为默认工程最优方案

## What Phase 3 Can Conclude Now

本阶段已经可以给出一个 `conditional yes`：

- `L2GridBook` 对“更深、更大、且 page 确实稠密”的 workload 不是伪命题
- 它在这类 workload 上确实能够出现优于 `L2TreeBook` 的可复现信号

但同时也必须保留下面这半句：

- 这个优势并不会因为 deep query 自己变重就自动在真实 sparse replay 上出现

也就是说，Phase 3 目前最准确的结论是：

- `grid` 的价值条件更像是 `density + depth`
- 而不是 `depth` 单独一个变量

## Exit Decision

Phase 3 的最小成功标准已经满足：

1. `real_shallow_control` 已跑完并落盘
2. `real_deep_query_sparse_replay` 已跑完并落盘
3. synthetic runner 已实现并可执行
4. dense / sparse synthetic 对照各至少跑出一轮结果

此外，本阶段还额外完成了：

- Phase 2 允许的 `q=100` 条件变体

因此 Phase 3 可以结束，并进入 Phase 4 的路线判断。

## Validation

本阶段已完成的验证：

- `cargo test -p nautilus-model l2_grid --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo test -p nautilus-tardis --test l2_book_parity`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo check -p nautilus-tardis --bin tardis-l2-synthetic-matrix`

## Bottom Line

Phase 3 最重要的价值，不是又多做了一个 benchmark。

而是它第一次把下面这句话变成了有证据支持的判断：

- `grid` 的路线价值并没有被完全否定，但它依赖真实成立的 dense page occupancy

这也意味着后续如果继续优化，应该优先围绕：

- 如何降低 sparse-case 的结构性惩罚
- 或者是否明确把 `grid` 定位成 dense/deep 专门结构

而不是再回去把“所有场景都想赢”当作默认目标。
