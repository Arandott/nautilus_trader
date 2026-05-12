# Phase 2: Minimal Workload Matrix For The Hypothesis

Date: 2026-04-09

## 目标

Phase 2 的任务不是继续优化 `L2GridBook`，而是把后续实验的 workload matrix 冻结下来，避免任务滑向无边界参数组合。

本阶段已经完成的事情：

- 冻结了 `4` 组 canonical workload family
- 为每组 workload 写清了要回答的问题、主要参数、运行入口状态、输出目录命名方式
- 定义了扩矩阵的触发条件和本阶段 exit criteria
- 给 Phase 3 留下了明确 handoff，而不是笼统地说“继续做 benchmark”

## 产物

- `2026-04-09_phase2_workload_matrix.md`
  - Phase 2 的主文档
  - 说明为什么只保留这 `4` 组 workload family
  - 说明每组 workload 想验证什么、如何判读
- `2026-04-09_phase2_workload_manifest.yaml`
  - machine-readable 的 workload manifest
  - 方便后续 Phase 3/5 按统一命名跑结果
- `2026-04-09_phase2_phase3_handoff.md`
  - 下一阶段的最小实现顺序
  - 说明哪些 workload 现在就能跑，哪些需要新增 runner

## 当前结论

Phase 2 的冻结结论是：

- 当前最小 workload matrix 应该保留 `4` 组 family，而不是继续扩大
- `real_shallow_control` 和 `real_deep_query_sparse_replay` 可以直接用现有 runner 执行
- `synthetic_dense_contiguous_home_court` 和 `synthetic_sparse_page_control` 需要在 Phase 3 新增 synthetic runner
- 在 dense / sparse synthetic 对照还没建立前，不应继续把主要精力放在 `PAGE_SIZE` 或 `best repair` 微调上

## 状态

按 Phase 2 自己的定义，这一阶段已经完成并可进入下一步。
