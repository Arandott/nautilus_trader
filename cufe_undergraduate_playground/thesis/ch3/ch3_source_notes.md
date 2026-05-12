# Chapter 3 Source Notes

用途：

- 本文件记录第三章正文背后的代码锚点、图示建议和后续整合提醒。
- 这些内容用于你后面整合总稿、补图和核对实现细节。
- 本文件不是论文正文，不应直接并入章节内容。

## 系统架构图建议

- 推荐放置位置：`3.2 系统总体设计`
- 推荐编号：`图3-1 本地 L2 订单簿维护系统总体架构图`
- 推荐作用：承接第三章开头的需求分析，并作为第四章实现说明的总入口
- Mermaid 初稿文件：`cufe_undergraduate_playground/thesis/ch3/fig_3_1_system_architecture.mmd`

### 图中建议包含的节点

1. 原始 L2 数据集
2. 数据解析与增量流生成
3. 统一 `delta` 语义
4. `L2BookOps` 抽象层
5. `baseline / L2TreeBook / L2VecBook / L2GridBook`
6. 查询与校验
7. benchmark / replay runner
8. 指标输出与结果汇总

### 推荐箭头关系

- 原始数据集 -> 数据解析与增量流生成
- 数据解析与增量流生成 -> `OrderBookDelta` / `OrderBookDeltas`
- 统一增量流 -> `L2BookOps`
- `L2BookOps` -> 四种订单簿实现
- 订单簿实现 -> 查询与校验
- 订单簿实现 -> replay / benchmark 统计
- replay / benchmark 统计 -> JSON 结果 / summary

### 画图时的核心口径

- 强调“统一输入”和“统一抽象”，不要画成四套彼此独立的小系统
- baseline 与三种特化结构应处于同一层级，因为它们共享同一实验闭环
- 图中不需要画得太细，不建议把具体函数名塞进架构图

## 第三章正文对应的主要代码与材料

1. 统一接口与基线/特化结构
   - `crates/model/src/orderbook/l2.rs`
   - `crates/model/src/orderbook/l2_vec.rs`
   - `crates/model/src/orderbook/l2_grid.rs`

2. microbench 入口
   - `crates/model/benches/l2_book_baseline_criterion.rs`

3. replay runner 入口
   - `crates/adapters/tardis/bin/l2_baseline.rs`

4. 结果汇总脚本
   - `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py`

5. 需求与口径材料
   - `plans/cufe_undergradution/workloads/workload_spec.md`
   - `plans/cufe_undergradution/correctness/correctness_spec.md`
   - `plans/cufe_undergradution/baseline/baseline_path_model.md`

## 第三章中需要特别注意的口径

1. 第三章写的是“系统需求分析与总体设计”。
   不要在这一章提前展开第四章级别的函数细节和字段解释。

2. 第三章写的是“系统”而不是“单个数据结构”。
   重点应放在输入、抽象边界、模块协同和验证闭环。

3. `L2TreeBook`、`L2VecBook`、`L2GridBook` 都要写成“有明确设计动机的路线”。
   不要在第三章提前把当前实验表现写成路线优劣裁决。

4. baseline 不能被写成“落后实现”。
   更稳的定位是：真实工程起点、对照实现和 correctness 参考实现。

5. 第三章要明确系统平台来源。
   更稳的写法是：本文系统基于 `NautilusTrader` 开源框架开发，在其既有数据模型、订单簿实现与实验环境之上进行扩展。
   不建议写成“从零实现完整交易系统”。

## 后续整合提醒

- 如果你后面要正式出图，我可以再帮你把图 3-1 细化成：
  - 方框图草案
  - Mermaid 版本
  - draw.io / PPT 文字布局稿
- 如果你后面要继续写第四章，我也可以直接沿着本文件中的代码锚点往下展开。
