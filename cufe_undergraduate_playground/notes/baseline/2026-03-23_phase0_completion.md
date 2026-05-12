# Phase 0 Completion Summary

日期：2026-03-23

## 结论

Phase 0 可以收尾。

我们已经完成了 baseline 路径建模、开销假设文档、统一 workload 定义、基础 benchmark harness，以及一组可复现的 baseline 数字。后续可以进入 `L2TreeBook` 实现阶段。

## 本阶段实际交付

- baseline 路径说明：
  - `plans/cufe_undergradution/baseline/baseline_path_model.md`
- 开销假设：
  - `plans/cufe_undergradution/baseline/baseline_overhead_hypotheses.md`
- workload 规格：
  - `plans/cufe_undergradution/workloads/workload_spec.md`
- 正确性规范：
  - `plans/cufe_undergradution/correctness/correctness_spec.md`
- Rust microbench：
  - `crates/model/benches/l2_book_baseline_criterion.rs`
- Rust replay runner：
  - `crates/adapters/tardis/bin/l2_baseline.rs`
- orchestration 脚本：
  - `cufe_undergraduate_playground/scripts/measurement/run_phase0_baseline.py`

## 本阶段主结果

### Microbench

结果文件：

- `cufe_undergraduate_playground/results/baseline/processed/criterion_estimates.json`

关键读数：

- `best_bid_ask`: `20.29 ns`
- `top_10_query`: `139.69 ns`
- `update_existing_level`: `72.20 ns`
- `delete_existing_level`: `210.62 ns`
- `insert_new_level`: `273.28 ns`

解释：

- baseline 的 best bid/ask 本来就很轻，这和前面的假设一致
- 更新和插入路径明显重于简单查询，说明后续优化更应该盯住 `apply_delta` 热路径，而不是先期待 best/top-N 大幅提升

### Real workload

主结果目录：

- `cufe_undergraduate_playground/results/baseline/phase0_subset_10m_r3_q100_q1000/`

输入配置：

- 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- 子集规模：前 `10,000,000` 条 delta
- 重复次数：`3`

汇总结果：

- `parse_only`
  - 平均耗时：`37.15 s`
  - 平均吞吐：`269.22k updates/s`
  - 平均峰值 RSS：`29.22 MB`
- `replay_only`
  - 平均耗时：`54.17 s`
  - 平均吞吐：`184.62k updates/s`
  - 平均峰值 RSS：`53.48 MB`
- `replay_periodic_query_q100`
  - 平均耗时：`55.01 s`
  - 平均吞吐：`181.80k updates/s`
  - 平均查询延迟：`3.22 us`
  - 平均峰值 RSS：`53.41 MB`
- `replay_periodic_query_q1000`
  - 平均耗时：`54.24 s`
  - 平均吞吐：`184.35k updates/s`
  - 平均查询延迟：`4.91 us`
  - 平均峰值 RSS：`53.44 MB`

## Phase 0 的有效判断

### 1. 解析与订单簿应用都重要

`parse_only` 到 `replay_only` 的吞吐从 `269.22k` 降到 `184.62k updates/s`。

这说明：

- CSV 解析不是零成本
- 但订单簿应用路径也有明确额外开销

因此后续 `L2TreeBook` 应当直接对准：

- `apply_delta` 热路径
- L2 不必要的抽象层
- 内存对象与容器成本

### 2. 低到中频查询不是 baseline 的主要矛盾

相对 `replay_only`：

- `q=100` 的总耗时只增加约 `1.55%`
- `q=1000` 的总耗时只增加约 `0.14%`

这说明在当前设定下：

- `best bid/ask + top-10` 的低到中频查询本身很轻
- baseline 的核心优化空间更可能在 replay/update，而不是 query API

### 3. 当前收益预期应保持“常数级优化”视角

结合代码分析和测量结果，Phase 1 更合理的目标不是一开始追求数量级提升，而是：

- 稳定提升 replay / update 吞吐
- 降低峰值内存与容器层次成本
- 在查询性能不退化的前提下验证 `L2` 专用语义的价值

## 为什么 Phase 0 现在可以结束

- baseline 文档体系已补齐
- baseline 测量工具链已能复用
- baseline 结果已有多次运行，不再依赖单次读数
- 下一阶段要优化的目标已经足够明确

换句话说，我们现在已经知道：

- baseline 在做什么
- baseline 可能慢在哪里
- baseline 真实 workload 下表现如何
- 后面该用什么口径评估 `L2TreeBook`

## Phase 1 入口

Phase 1 的首要目标：

- 实现 `L2TreeBook`
- 使用与 baseline 完全相同的输入、workload 和正确性规则
- 优先比较：
  - `update_existing_level`
  - `insert_new_level`
  - `delete_existing_level`
  - `replay_only`
  - `replay_periodic_query_q100`

这将是对“L2 专用语义是否已经有稳定收益”的第一轮验证。
