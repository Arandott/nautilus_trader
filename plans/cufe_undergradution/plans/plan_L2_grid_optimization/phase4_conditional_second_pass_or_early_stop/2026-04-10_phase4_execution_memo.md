# Phase 4 Execution Memo

日期：2026-04-10

## 目标

Phase 4 只做一件事：

- 用一个低到中风险的结构压缩项，验证 `L2GridBook` 能不能显著缓解 sparse-case 的结构性惩罚。

本轮选择的压缩项是：

- 去掉 slot 内保存的完整 `Price`
- 让 `price = base_tick + slot` 变成派生值
- 每个 slot 只保留 `Quantity + price_precision`

## 实施内容

代码改动落在：

- `crates/model/src/orderbook/l2_grid.rs`

具体变化：

1. `GridLevel` 从 `Price + Quantity` 改成 `Quantity + price_precision`
2. `GridPage::upsert` 不再写入完整 `Price`，只记录 `price_precision`
3. `GridPage::level_at` / `visit_levels` 在读取路径上按 `slot_tick` 派生 `Price`
4. 新增一个单元测试，确认“按 slot tick + precision 派生出的 price”等于原始 price

## 验证范围

### 编译与测试

已执行：

- `source .venv/bin/activate && cargo test -p nautilus-model l2_grid --lib`
- `source .venv/bin/activate && LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} cargo test -p nautilus-tardis --test l2_book_parity`
- `source .venv/bin/activate && cargo check -p nautilus-model --bench l2_book_baseline_criterion`
- `source .venv/bin/activate && cargo check -p nautilus-tardis --bin tardis-l2-synthetic-matrix`

### Workload 回归

本轮沿用 Phase 2 冻结矩阵，只复测 `l2grid`：

- `real_shallow_control`
- `real_deep_query_sparse_replay` (`depth=500`, `q=100`)
- `synthetic_dense_contiguous_home_court`
- `synthetic_sparse_page_control`

说明：

- `baseline` / `l2tree` / `l2vec` 在本轮没有改代码，所以相对排名仍以 Phase 3 冻结结果为参考。
- 这意味着 Phase 4 的核心判断是“新的 `l2grid` 相比旧的 `l2grid` 是否更接近可用”，而不是生成一套全新 authoritative 横评。

## 布局结果

布局诊断输出：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/layout/l2_grid_diagnostics_limit100k.json`

关键变化：

| 指标 | Phase 1 / 旧值 | Phase 4 / 新值 | 变化 |
|---|---:|---:|---:|
| `grid_level_size_bytes` | 64 | 48 | -25.0% |
| `option_grid_level_size_bytes` | 80 | 64 | -20.0% |
| `grid_page_size_bytes` | 5152 | 4128 | -19.9% |
| `bytes_per_active_level` at occupancy=1 | 5152 | 4128 | -19.9% |

结论：

- 这轮压缩在静态布局层面是成立的。
- page 固定成本被明显打下来了。
- occupancy 仍然没有变化；真实 sparse replay 里 populated page 依然基本是 `1 page = 1 level`。

## Workload 对比

### 1. 真实浅簿控制组

文件：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_shallow_control_btcusdt_10m/l2grid.json`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/real_shallow_control_btcusdt_10m/l2grid.json`

结果：

| 指标 | Phase 3 / 旧 `l2grid` | Phase 4 / 新 `l2grid` | 变化 |
|---|---:|---:|---:|
| `updates_per_sec` | 178,377.40 | 190,175.17 | +6.61% |
| `peak_resident_mb` | 249.97 | 206.13 | -17.54% |

判读：

- 真实浅簿控制组上，压缩确实带来了可感知的 throughput 改善和明显的 RSS 改善。
- 但它仍然落后于 `l2tree` 的 `231,061.70 updates/s`，且 RSS 仍高于 `l2tree` 的 `32.61 MB`。

### 2. 真实深查询稀疏 replay

文件：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_deep_query_sparse_replay_btcusdt_10m/depth500_q100/l2grid.json`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/real_deep_query_sparse_replay_btcusdt_10m/depth500_q100/l2grid.json`

结果：

| 指标 | Phase 3 / 旧 `l2grid` | Phase 4 / 新 `l2grid` | 变化 |
|---|---:|---:|---:|
| `updates_per_sec` | 133,305.51 | 160,245.90 | +20.21% |
| `avg_query_ns` | 104,170 | 103,915 | -0.24% |
| `peak_resident_mb` | 249.77 | 206.16 | -17.46% |

对 `l2tree` 的相对位置：

- `l2tree` throughput: `181,913.70 updates/s`
- `l2tree` avg query: `75,957 ns`
- `l2tree` peak RSS: `32.57 MB`

判读：

- 这轮压缩对真实 sparse replay 的吞吐改善是明确的。
- 但 query 几乎没有改善，`l2grid` 仍比 `l2tree` 慢约 `36.8%`。
- 相对排名没有翻转，只是把差距缩小了。

### 3. dense synthetic home court

文件：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_dense_contiguous_home_court_1024lvl/depth500_q100/l2grid.json`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/synthetic_dense_contiguous_home_court_1024lvl/depth500_q100/l2grid.json`

结果：

| 指标 | Phase 3 / 旧 `l2grid` | Phase 4 / 新 `l2grid` | 变化 |
|---|---:|---:|---:|
| `updates_per_sec` | 600,664.85 | 569,455.47 | -5.20% |
| `avg_query_ns` | 15,311 | 28,990 | +89.34% |
| `peak_resident_mb` | 16.73 | 16.55 | -1.07% |

对 `l2tree` 的相对位置：

- `l2tree` throughput: `478,681.44 updates/s`
- `l2tree` avg query: `69,790 ns`

判读：

- `grid` 在 dense case 的正信号还在，仍然比 `l2tree` 更快。
- 但读取路径按 slot 派生 `Price` 的代价开始显现，deep query 明显变慢。
- 这说明本轮压缩不是纯收益，它在“降低固定成本”和“增加读取常数”之间做了交换。

### 4. sparse synthetic control

文件：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_sparse_page_control_1024lvl/depth500_q100/l2grid.json`
- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase4/synthetic_sparse_page_control_1024lvl/depth500_q100/l2grid.json`

结果：

| 指标 | Phase 3 / 旧 `l2grid` | Phase 4 / 新 `l2grid` | 变化 |
|---|---:|---:|---:|
| `updates_per_sec` | 359,989.52 | 352,399.01 | -2.11% |
| `avg_query_ns` | 65,408 | 83,320 | +27.39% |
| `peak_resident_mb` | 31.49 | 28.59 | -9.23% |

对 `l2tree` 的相对位置：

- `l2tree` throughput: `479,546.91 updates/s`
- `l2tree` avg query: `69,617 ns`
- `l2tree` peak RSS: `16.80 MB`

判读：

- 低 occupancy synthetic 对照里，内存改善成立，但 runtime 没有被救回来。
- `l2grid` 依然明显输给 `l2tree` throughput，而且 query 也变得更慢。
- 这说明单次 page 体积压缩不足以解决 sparse-case economics。

## 是否满足早停条件

Phase 3 handoff 允许的早停条件包括：

1. 第一轮结构压缩后，dense case 改善有限，但 sparse case 仍没有实质改善
2. 继续推进需要大规模改写 page representation，已经超出当前任务边界

本轮结果对应判断：

- dense case 没有继续改善，反而在 query 上明显回退
- sparse synthetic 没有被修复
- 真实 sparse replay 虽然吞吐改善，但仍没有改变“默认方案仍应是 `l2tree`”这一判断

因此：

- **Phase 4 已经满足“可以尽早停下”的条件。**

## 本阶段结论

本轮压缩回答得很明确：

- `GridPage` 的静态固定成本确实太大，压缩它是对的
- 但“去掉 slot 内完整 `Price`”只解决了内存和一部分真实 sparse 吞吐
- 它没有把 `grid` 从 dense/deep 候选结构变成默认工程实现
- 如果要继续追 sparse-case economics，下一步就不是小修，而是 page representation 级别的更大改写

所以更合适的动作不是继续堆 Phase 4 的小优化，而是进入 Phase 5，正式收束结论：

- 默认工程方案：继续 `L2TreeBook`
- 专项结构候选：`L2GridBook` 只在 dense + deep workload 下保留研究价值
