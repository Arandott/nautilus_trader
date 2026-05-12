# Baseline 建模详细执行计划

日期：2026-03-23

项目阶段：Phase 0

## 1. 阶段目标

Phase 0 的目标不是实现新的 `L2Book`，而是建立一套可信、可复现、可扩展的 baseline 建模与测量体系。

完成本阶段后，我们应当能够：

- 清楚描述原生 `nautilus_trader` 的 `L2_MBP` 更新路径
- 明确写出 baseline 的潜在开销项与性能假设
- 用同一份原始 `delta` 稳定驱动 baseline
- 得到第一版可复现的 benchmark / profiling 结果
- 为后续 `L2TreeBook / L2VecBook / L2GridBook` 预留统一实验框架

## 2. 本阶段交付物

### 2.1 计划与说明类

- `phase0_baseline_modeling_plan.md`
  - 本文件，定义 Phase 0 的目标、结构、输出和完成标准
- `baseline_path_model.md`
  - 梳理原生 `L2_MBP` 的调用链、核心结构、关键代码位置
- `baseline_overhead_hypotheses.md`
  - 记录预期开销、影响路径、验证方法
- `workload_spec.md`
  - 定义 microbench 与真实 workload
- `correctness_spec.md`
  - 定义结果一致性标准

### 2.2 工程与脚本类

- baseline benchmark harness 原型
- baseline replay / measurement 脚本
- profiling 运行脚本或命令记录
- 结果收集模板

### 2.3 结果类

- 第一版 baseline microbench 结果
- 第一版 baseline 全日 replay 结果
- 第一版 profiling 观察记录
- 第一版实验日志与结论摘要

## 3. 工程骨架架构

本阶段的工程文件统一放在 `cufe_undergraduate_playground/` 下，建议结构如下：

```text
cufe_undergraduate_playground/
  scripts/
    data/
    measurement/
    analysis/
  benchmarks/
    micro/
    workloads/
    harness/
  experiments/
    configs/
    runners/
  results/
    baseline/
      raw/
      processed/
      summaries/
    l2tree/
    l2vec/
    l2grid/
    comparisons/
  figures/
    baseline/
    comparisons/
  notes/
    baseline/
```

各目录职责：

- `scripts/data/`
  - 数据读取、小型转换、输入检查等辅助脚本
- `scripts/measurement/`
  - 指标采集、结果标准化、统计汇总脚本
- `scripts/analysis/`
  - 结果解析、简单表格生成、画图前处理
- `benchmarks/micro/`
  - 单操作或短序列 microbench
- `benchmarks/workloads/`
  - 真实 workload 的 benchmark 驱动
- `benchmarks/harness/`
  - baseline 与后续 proposed 共用的驱动层
- `experiments/runners/`
  - 运行 replay、定期查询、profiling 的脚本
- `experiments/configs/`
  - 数据路径、采样频率、查询频率、输出目录等配置
- `results/baseline/raw/`
  - benchmark 原始输出、日志、profile 原始文件
- `results/baseline/processed/`
  - 整理后的 CSV、JSON、Markdown 表格
- `results/baseline/summaries/`
  - baseline 阶段小结与读数说明
- `notes/baseline/`
  - 手工分析笔记、观察记录、问题排查日志

说明：

- `cufe_undergraduate_playground/` 不承载 Rust 主源码
- 如果需要实现或修改 Rust 订单簿逻辑，应直接在 `crates/` 下进行
- playground 主要承载实验脚本、测量逻辑、结果与分析材料

## 4. 脚本架构

本阶段不追求脚本很多，而追求职责清晰。建议最小脚本集合如下：

### 4.1 数据与驱动层

- `experiments/runners/load_l2_dataset.*`
  - 负责读取原始 `delta` 数据
  - 输出统一的迭代流或 batch

- `experiments/runners/replay_baseline.*`
  - 将数据顺序喂给原生 baseline
  - 支持记录总耗时、吞吐、内存

### 4.2 测量层

- `experiments/runners/run_microbench.*`
  - 运行 microbench
  - 支持不同 workload 和重复次数

- `experiments/runners/run_profile.*`
  - 统一包装 profiling 命令
  - 输出热点记录与运行环境信息

- `experiments/runners/run_workloads.*`
  - 运行真实 workload
  - 统一组织 replay-only、replay+query、replay+feature

### 4.3 汇总层

- `experiments/runners/collect_results.*`
  - 收集 raw 结果
  - 标准化到统一格式

- `experiments/runners/summarize_results.*`
  - 生成简单表格和阶段总结

## 5. 文档记录内容要求

### 5.1 `baseline_path_model.md`

必须记录：

- 原生 `L2_MBP` 的输入对象与入口
- `aggregation -> ladder -> level` 的核心路径
- `synthetic order_id` 的产生位置
- `cache`、`BookLevel.orders`、`BTreeMap` 各自的作用
- best bid/ask 与 top-N 的获取方式
- 关键代码文件与行号

### 5.2 `baseline_overhead_hypotheses.md`

每个开销项都应包含：

- 名称
- 代码位置
- 为什么怀疑它有额外开销
- 影响哪些 workload
- 预期被哪类 proposed 方案削减
- 用什么 benchmark / profiling 验证

推荐优先记录：

- `price -> synthetic order_id`
- `order_id -> BookPrice cache`
- `BookLevel.orders: IndexMap`
- order 语义残留
- `add/update/delete(order)` 路径

### 5.3 `workload_spec.md`

必须明确：

- 数据集路径
- 输入数据规模
- microbench 名称与定义
- 真实 workload 名称与定义
- 查询频率设置
- 输出指标
- 每个 workload 想解释什么问题

### 5.4 `correctness_spec.md`

必须明确：

- best bid/ask 如何比较
- top-N 如何比较
- `quantity_at(price)` 如何比较
- 全量 replay 最终状态如何比较
- 抽样比对频率
- 错误日志如何保存

### 5.5 `results/baseline/summaries/`

每次测量至少记录：

- 日期
- commit id
- 数据集
- 运行命令
- 机器环境
- 结果摘要
- 异常现象
- 对下一步实现的启发

## 6. Workload 最小集合

### 6.1 Microbench

第一批必须覆盖：

- `update_existing_level`
- `insert_new_level`
- `delete_existing_level`
- `best_bid_ask`
- `top_10_query`

可选补充：

- `quantity_at_price`
- 短批量 `apply_deltas`

### 6.2 真实 workload

第一批必须覆盖：

- `Full-day replay`
- `Replay + periodic top-N query`

第二批可扩展：

- `Replay + feature extraction`
- `Windowed reconstruction`

## 7. 结果指标

本阶段至少要稳定产出这些指标：

- 总耗时
- updates/s
- 峰值内存
- 平均延迟或单操作耗时
- 不同查询频率下的 replay 开销变化
- profiling 热点占比

如果工具链允许，建议补充：

- allocation 次数
- cache miss 相关观测
- 热点函数调用占比

## 8. 执行顺序

建议执行顺序如下：

1. 写 `baseline_path_model.md`
2. 写 `baseline_overhead_hypotheses.md`
3. 写 `workload_spec.md`
4. 写 `correctness_spec.md`
5. 搭 baseline replay 脚本
6. 搭第一版 microbench harness
7. 跑第一版 baseline 数据
8. 记录 profiling 观察
9. 输出 Phase 0 总结

## 9. 完成标准

本阶段完成的判断标准：

- baseline 路径模型已经写清楚
- 开销假设表已经成文，且能映射到后续优化方向
- 至少一份数据集可以稳定驱动 baseline replay
- 至少一组 microbench 与一组真实 workload 已完成
- 已产出第一版结果文件和总结文件
- 后续 `L2TreeBook` 已有明确插入点和比较框架

## 10. 风险与控制

主要风险：

- 过早进入实现，导致 baseline 理解不扎实
- benchmark harness 过度设计，拖慢推进
- profiling 工具选择过重，影响第一周节奏
- 结果记录不规范，后面无法复现

控制策略：

- 先文档化 baseline，再写脚本
- Phase 0 只做最小可用 harness
- 先拿到第一版粗粒度结果，再逐步细化 profiling
- 每次运行都强制记录配置、命令和输出目录

## 11. Phase 0 推荐首批文件

建议首先补齐这些文件：

- `plans/cufe_undergradution/baseline/baseline_path_model.md`
- `plans/cufe_undergradution/baseline/baseline_overhead_hypotheses.md`
- `plans/cufe_undergradution/workloads/workload_spec.md`
- `plans/cufe_undergradution/correctness/correctness_spec.md`
- `cufe_undergraduate_playground/experiments/runners/replay_baseline.*`
- `cufe_undergraduate_playground/experiments/runners/run_microbench.*`
- `cufe_undergraduate_playground/results/baseline/summaries/baseline_summary.md`

## 12. 本阶段结论

Phase 0 的本质是“把 baseline 看透、测准、记清楚”。只有这一层做扎实，后续 `L2TreeBook / L2VecBook / L2GridBook` 的提升才会有解释力，也才有论文价值。
