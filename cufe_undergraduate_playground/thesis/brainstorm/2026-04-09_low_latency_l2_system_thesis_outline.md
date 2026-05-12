# 面向低延迟交易的本地 L2 订单簿维护系统论文大纲

日期：2026-04-09

## 目的

本文档用于把现有工程、实验结果和论文写作骨架对齐，形成一份可直接展开正文的毕业论文大纲。

当前论文题目应统一表述为：

- `面向低延迟交易的本地 L2 订单簿维护系统`

## 写作总原则

整篇论文应坚持以下叙事原则：

1. 论文主线是“面向低延迟交易的本地 L2 订单簿维护系统”，而不是单纯的数据结构跑分比较。
2. `baseline`、`L2TreeBook`、`L2VecBook`、`L2GridBook` 都是系统中的实现或对照对象，而不是孤立存在的 benchmark case。
3. `L2TreeBook`、`L2VecBook`、`L2GridBook` 三种设计都要写清楚其设计动机、适用假设和工程目标。
4. 写作中要明确区分三层含义：
   - 设计动机是否成立
   - 当前实现是否成熟
   - 当前实验结果是否已经充分兑现设计预期
5. 对 `L2VecBook`、`L2GridBook` 的表述应保持客观：
   - 不是“设计无价值”
   - 而是“当前实现与参数调优尚未完全兑现其潜在优势”
6. 结果分析部分要如实呈现阶段性事实，但不能把“当前最优实现”写成“唯一合理设计”。

## 前置部分

- 封面
- 声明
- 中文摘要
- Abstract
- 目录

前置部分写作提示：

- 中文摘要和 Abstract 都应围绕“低延迟交易场景下的本地 L2 订单簿维护”展开。
- 摘要中应突出：
  - 研究背景是低延迟交易对本地订单簿维护效率的要求
  - 问题是通用订单簿在 `L2_MBP` 场景下存在额外抽象开销
  - 方法是设计统一接口下的多种 L2 特化结构并完成对比验证
  - 结果是当前 `L2TreeBook` 最成熟，`L2VecBook` 与 `L2GridBook` 揭示了进一步优化的方向与约束

## 第一章 绪论

### 1.1 课题背景

本节应回答“为什么要做这个系统”。

建议写入的内容：

- 低延迟交易、量化研究和本地回放场景对订单簿维护提出了高吞吐、低时延、低内存占用要求。
- L2 订单簿是很多交易决策、盘口特征提取和本地仿真的核心数据基础。
- 交易所原始增量数据通常以 `delta` 流形式到达，本地系统必须高效完成解析、维护、查询与重建。
- 通用订单簿实现虽然功能完备，但在纯 `L2_MBP` 场景下可能保留了不必要的抽象与路径成本。
- 因而有必要围绕低延迟交易目标，构建一个面向 L2 的本地维护系统。

### 1.2 国内外研究现状

本节应从“系统与技术路径”角度综述，不必只盯着单一数据结构。

建议组织为三部分：

- 本地订单簿维护与市场数据处理系统研究现状
- 低延迟交易系统中常见的数据组织与内存优化思路
- 面向订单簿不同层级 `L1/L2/L3` 的数据结构设计差异

本节要自然引出的问题：

- 现有工作往往强调通用性、功能完备性或单点性能，但未必专门针对 `L2_MBP` 的本地低延迟维护场景做结构压缩。
- 低延迟系统设计不仅要看单个 query 跑分，还要看真实 replay、动态插删、内存占用和正确性闭环。

### 1.3 研究意义、研究内容与研究目标

本节建议拆成三小层。

研究意义：

- 理论意义：讨论面向 `L2_MBP` 的结构特化是否能有效降低通用订单簿的路径开销。
- 工程意义：为低延迟交易和本地研究提供更轻量、更高效的订单簿维护方案。
- 方法意义：建立统一的 correctness、microbench 和 replay workload 验证框架。

研究内容：

- 建模并分析原生 `OrderBook(BookType::L2_MBP)` 的 baseline 路径与潜在开销。
- 抽象统一的 `L2BookOps` 接口。
- 实现并对比 `L2TreeBook`、`L2VecBook`、`L2GridBook` 三种 L2 特化结构。
- 构建 microbench 与真实 replay workload。
- 建立正确性验证、性能测量与结果汇总链路。

研究目标：

- 在相同原始 `delta` 输入下，探索更适合低延迟交易场景的本地 L2 维护结构。
- 在吞吐、时延、内存占用和一致性之间寻找更优工程平衡点。
- 形成一个可复现、可扩展的本地 L2 订单簿维护系统原型。

### 1.4 论文结构

本节简要说明六章安排即可：

- 第一章提出问题
- 第二章铺设技术基础
- 第三章分析需求并设计系统
- 第四章介绍系统实现
- 第五章进行测试与结果分析
- 第六章总结全文并给出展望

## 第二章 相关技术与理论基础

### 2.1 L2 订单簿与本地维护问题定义

本节建议定义清楚：

- `L1 / L2 / L3` 的区别
- `MBP` 与 `MBO` 的区别
- 本文中的 L2 对象是 `price level aggregate`，而非逐笔订单队列
- 本地维护系统的输入是交易所原始 `delta`
- 本地维护系统的核心任务包括：
  - 增量更新
  - 最优价查询
  - top-N 查询
  - 顺序重建
  - 为策略或研究提供特征计算基础

### 2.2 原生订单簿实现机制与 baseline 技术基础

本节建议介绍当前 baseline 的技术基础，为后文改进做铺垫。

重点可写：

- 原生 `OrderBook(BookType::L2_MBP)` 的整体结构
- `BookLadder`、`BookLevel`、`synthetic order_id`、`cache` 的作用
- 原生路径如何把 L2 输入映射到通用订单簿语义
- baseline 已经具备哪些优势：
  - 有序 price level 组织
  - 较直接的 best bid/ask 获取路径
- baseline 在 L2 场景下仍残留哪些额外抽象

这里要避免把 baseline 写得过于“落后”，应写成：

- 它是通用系统中的合理设计
- 但在纯 L2、本地低延迟维护目标下仍有进一步专门化空间

### 2.3 低延迟本地维护涉及的关键技术

本节可以作为第三章设计的知识前提。

建议覆盖：

- 有序树结构与动态插删
- 连续内存布局与 cache locality
- tick 离散化、索引映射与 page/bitmap 思路
- 增量回放与状态重建
- correctness 验证与 replay parity
- microbench 与 end-to-end workload 的差异

这一节的写法重点是给后面三种设计提供理论动机：

- 为什么会想到树
- 为什么会想到向量
- 为什么会想到 grid

### 2.4 本章小结

本节收束方式：

- 第二章不是给出结论，而是明确第三章系统设计将面对的概念边界和技术选择空间。

## 第三章 系统需求分析与总体设计

### 3.1 系统需求分析

本节建议分为功能需求与非功能需求。

功能需求：

- 支持接收并顺序处理原始 L2 `delta`
- 支持本地订单簿状态维护
- 支持 best bid/ask、top-N 等核心查询
- 支持 replay-only 与 replay+query 场景
- 支持不同 L2 结构在同一输入下可切换运行
- 支持结果记录、正确性验证与性能汇总

非功能需求：

- 低时延
- 高吞吐
- 内存占用可控
- 正确性可验证
- 架构可扩展
- 结果可复现

### 3.2 系统总体设计

本节建议给出系统总体框图。

系统主线可描述为：

1. 原始数据集输入
2. 统一解析为增量 `delta` 流
3. 通过统一接口驱动不同订单簿实现
4. 执行查询或特征操作
5. 记录运行指标与正确性结果
6. 汇总结果并用于论文分析

总体设计中应强调：

- 原始 `delta` 是统一输入与 `source of truth`
- `L2BookOps` 是系统内部的抽象边界
- baseline 与三种特化结构都在同一实验闭环内

### 3.3 功能模块设计

建议将系统拆为以下模块：

- 数据输入与解析模块
- 订单簿核心维护模块
- 查询与校验模块
- benchmark 与 replay 运行模块
- 结果采集与汇总模块

每个模块下可说明：

- 输入输出
- 与其他模块的调用关系
- 在系统中的职责

### 3.4 系统设计优劣分析

本节建议写系统级优点，而不是只谈数据结构优缺点。

可写优点：

- 采用统一接口，便于在同一 workload 下公平比较
- 保留 baseline，便于建立对照
- 以增量回放为中心，符合低延迟交易的真实处理路径
- correctness 与性能测量一起设计，结论更稳健

可写局限：

- 当前以单一主数据集为核心
- 当前系统仍偏研究型验证平台，而非完整生产交易平台
- 部分设计已提出但尚未被完全优化

### 3.5 设计中的制约因素

本节很重要，能让论文更真实。

建议写：

- 不能为了优化 L2 而破坏统一输入语义
- 需要保持与 baseline 的可比性
- 需要尽量减少对主仓库已有系统的侵入
- 需要在有限时间内完成实现、验证与写作
- 数据集规模、环境配置和测试成本都会影响迭代速度

### 3.6 成本或工作量估算

本节可以从工程实施角度写，不需要财务化。

建议写成：

- baseline 建模与路径分析工作量
- 三种 L2 结构的实现工作量差异
- 正确性验证与 benchmark harness 的构建成本
- 真实 replay 测量和结果整理成本

也可以写成一张表：

- 模块名称
- 实现复杂度
- 测试复杂度
- 调优难度

### 3.7 本章小结

本节收束重点：

- 第三章完成了从需求到总体设计的过渡，第四章将进入具体实现。

## 第四章 系统实现

### 4.1 实现基础

本节说明实现环境与实现组织方式。

建议写：

- 核心实现位于 Rust 仓库 `crates/`
- 实验脚本、结果、幻灯片材料位于 `cufe_undergraduate_playground/`
- benchmark 基于 Criterion
- replay runner 基于 Tardis CSV 数据流
- 结果处理由 Python 脚本完成

### 4.2 统一接口与公共机制实现

本节是第四章的关键入口。

应重点介绍：

- `L2BookOps` 接口的设计目的
- 为什么要让 baseline 与三种 L2 特化结构共享同一接口
- `apply_delta`、`best_bid_ask`、`top_n_levels` 等核心操作
- replay runner 如何通过 `--book` 切换不同实现
- criterion bench 如何统一测试五类 microbench case

### 4.3 Baseline 集成与对照实现

本节不要只把 baseline 当背景，应把它作为系统中的对照实现写清楚。

建议内容：

- 原生 `OrderBook(BookType::L2_MBP)` 的集成方式
- baseline 为什么可以接入 `L2BookOps`
- baseline 在系统中的角色：
  - 正确性参考实现
  - 性能对照实现
  - 通用语义代表实现

### 4.4 `L2TreeBook` 实现

本节建议按“设计动机 -> 数据结构 -> 核心操作 -> 工程特点”展开。

应重点写：

- 设计动机：先验证 L2 专用语义本身的收益
- 核心结构：`BTreeMap<BookPrice, Quantity>`
- 为什么保留有序树：
  - best bid/ask 直接
  - top-N 遍历稳定
  - 对动态插删更稳健
- `upsert/delete/clear` 等核心路径
- 当前它为什么是最成熟的一版

### 4.5 `L2VecBook` 实现

本节必须把设计动机写充分。

应重点写：

- 设计动机：利用连续内存布局与 query locality，探索是否能进一步降低查询开销
- 核心结构：`Vec<(Price, Quantity)>`
- 有序定位、插入、删除的实现方式
- 它适合的假设：
  - 盘口较浅
  - 结构较稳定
  - 查询密度较高
- 当前实现的主要限制：
  - 中间插删需要搬移元素
  - 动态更新路径还没有充分优化

这里的口径应是：

- `L2VecBook` 是带有明确目标的设计
- 当前主要问题是“动态路径优化仍不充分”，不是“思路没有意义”

### 4.6 `L2GridBook` 实现

本节建议写得更细，因为它最有“系统设计研究感”。

应重点写：

- 设计动机：利用 tick 离散化进一步削减树比较与 level 级节点开销
- 从早期 tick-keyed prototype 到 chunked sparse-grid 的演进
- 核心结构：
  - `SideGrid`
  - `pages`
  - `GridPage`
  - `occupancy_bitmap`
  - `best_page` / `best_tick`
- price 到 `(page_id, slot)` 的映射
- page 内扫描与跨页 best 修复逻辑
- 当前实现的价值：
  - 已经完成真正的 grid 化表达
  - 已经形成可测、可验证的工程版本
- 当前实现仍待优化的点：
  - page size
  - page 索引结构
  - page pooling / reuse
  - 稀疏页带来的内存放大

### 4.7 正确性验证模块实现

本节建议突出“性能比较之前先证明结果没变”。

可写内容：

- baseline 作为参考实现
- parity test 的设计
- best bid/ask、top-N、最终状态、采样 price quantity 的对比
- model-level unit test 与 Tardis replay parity 的配合
- 为什么 correctness 是系统可信性的前提

### 4.8 Benchmark 与 replay 测量模块实现

本节建议介绍两层测量机制：

- microbench
- real workload

应写内容：

- 五个 microbench case 的定义
- `replay_only` 与 `replay_periodic_query` workload
- 输出指标：
  - elapsed time
  - updates/s
  - peak RSS
  - query latency
- 结果输出、JSON 汇总、Markdown summary 的形成流程

### 4.9 结果处理与面向写作的分析支撑实现

本节可承接实验结果到论文图表。

建议写：

- Python 汇总脚本如何生成 `runner_summary.json`、`criterion_summary.json`
- 中期汇报图表数据如何导出
- 实验记录如何沉淀为论文可引用材料

这部分能说明：

- 系统不仅能跑
- 还能稳定产出可比较、可写入论文的结构化结果

### 4.10 本章小结

本节收束重点：

- 第四章完成了从总体设计到实际系统实现的落地。

## 第五章 测试与结果分析

### 5.1 测试环境

本节建议说明：

- 运行环境
- 编译与测试工具链
- 数据集路径与规模
- repeats 和 query interval 设置
- benchmark 与 replay 运行方式

可直接围绕当前统一配置写：

- dataset：`binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit：`10_000_000`
- repeats：`3`
- depth：`10`
- workloads：`replay_only`、`replay_periodic_query(q=100)`、`replay_periodic_query(q=1000)`

### 5.2 测试设计、测试结果与结果分析

这一节建议内部再拆成几个小层。

#### 5.2.1 正确性测试设计与结果

建议写：

- 单元测试
- parity 测试
- replay 一致性验证
- 当前三种特化结构都已接入统一 correctness 链路

#### 5.2.2 Microbench 测试设计与结果

应分析五类操作：

- `update_existing_level`
- `insert_new_level`
- `delete_existing_level`
- `best_bid_ask`
- `top_10_query`

建议分析思路：

- baseline 与三种结构在不同原子操作上的优劣差异
- 为什么单点 query 优秀并不必然代表 replay 更快
- 为什么 insert/delete 的常数会显著影响 end-to-end 效果

#### 5.2.3 真实 replay workload 测试设计与结果

重点写：

- `replay_only`
- `replay_periodic_query`
- 吞吐、耗时、峰值内存

这里可以呈现当前阶段性的核心结论：

- `L2TreeBook` 当前综合表现最佳
- `L2VecBook` 在 query 侧有优势，但 replay 侧尚未兑现
- `L2GridBook` 已有明确结构特化意义，但当前版本仍受 page sparsity 和对象粒度影响

#### 5.2.4 三种设计的综合分析

本小节建议按“设计目标是否被当前实现兑现”来写。

`L2TreeBook`：

- 已较充分兑现“去除 L2 无关抽象并获得稳定收益”的目标

`L2VecBook`：

- 已验证连续内存与查询局部性在 query microbench 上有效
- 但动态插删路径的代价仍限制了其在真实回放中的表现

`L2GridBook`：

- 已验证基于 tick 离散化进行更激进结构设计是可实现的
- 但当前 page/index/内存管理策略仍需进一步调优

这一节应特别注意：

- 结论必须写成“当前实现阶段的实验结论”
- 不能把“尚未优化完全”误写成“设计本身错误”

### 5.3 本章小结

本节建议总结为：

- 系统已经形成完整测试与验证闭环
- 当前最成熟实现是 `L2TreeBook`
- `L2VecBook` 与 `L2GridBook` 为后续低延迟优化提供了继续演进的技术方向

## 第六章 总结与展望

### 6.1 全文总结

本节可总结本文完成的工作：

- 建立了面向低延迟交易的本地 L2 订单簿维护系统原型
- 完成了 baseline 路径建模
- 设计并实现了三种面向 L2 的特化订单簿结构
- 建立了统一 correctness、microbench 和 replay workload 验证框架
- 获得了阶段性的工程结论与性能结果

### 6.2 主要结论

建议提炼为：

1. 面向 `L2_MBP` 做结构特化是有意义的。
2. 低延迟系统优化不能只看静态查询性能，还必须看真实 replay 路径。
3. 不同结构各有明确设计动机，当前差异更多体现为实现成熟度与适用假设差异。
4. 当前阶段 `L2TreeBook` 是最成熟的系统实现，但这并不否定 `L2VecBook` 和 `L2GridBook` 的后续优化价值。

### 6.3 后续展望

建议写：

- 继续优化 `L2VecBook` 的动态插删路径
- 继续优化 `L2GridBook` 的 page 大小、索引结构与内存复用
- 增加更多日期、更多品种与更多市场状态的数据集
- 扩展 `replay + feature extraction` 与 `windowed reconstruction`
- 进一步探索与本地持久化、策略研究流程的系统级集成

## 后置部分

- 致谢
- 参考文献
- 附录

附录中可考虑放入：

- 关键命令
- 结果目录结构
- 主要实验配置
- 关键数据结构伪代码或补充流程图

## 现有材料到论文章节的映射

下面这些现有文档可以直接为正文服务。

第一章、第二章可复用材料：

- `plans/cufe_undergradution/plans/2026-03-23_l2_book_optimization_plan.md`
- `plans/cufe_undergradution/brainstorm/2026-03-22_l2_book_brainstorm.md`
- `plans/cufe_undergradution/baseline/baseline_path_model.md`
- `plans/cufe_undergradution/baseline/baseline_overhead_hypotheses.md`

第三章可复用材料：

- `plans/cufe_undergradution/workloads/workload_spec.md`
- `plans/cufe_undergradution/correctness/correctness_spec.md`
- `cufe_undergraduate_playground/README.md`

第四章可复用材料：

- `crates/model/src/orderbook/l2.rs`
- `crates/model/src/orderbook/l2_vec.rs`
- `crates/model/src/orderbook/l2_grid.rs`
- `plans/cufe_undergradution/implementation/phase2/2026-03-24_phase2_l2vecbook_devlog.md`
- `plans/cufe_undergradution/implementation/phase3/2026-03-24_phase3_l2gridbook_devlog.md`

第五章可复用材料：

- `crates/model/benches/l2_book_baseline_criterion.rs`
- `crates/adapters/tardis/bin/l2_baseline.rs`
- `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py`
- `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`
- `cufe_undergraduate_playground/notes/phase3/2026-03-24_phase3_refresh_summary.md`
- `cufe_undergraduate_playground/thesis/brainstorm/2026-04-09_l2_orderbook_engineering_status.md`

第六章可复用材料：

- `cufe_undergraduate_playground/thesis/brainstorm/2026-04-09_l2_orderbook_engineering_status.md`
- `cufe_undergraduate_playground/notes/phase3/2026-03-24_phase3_refresh_summary.md`

## 当前推荐的写作顺序

如果要正式开始写正文，推荐按下面顺序推进：

1. 先写第三章和第四章，因为这两章最依赖现有工程材料，且内容最扎实。
2. 再写第五章，把已有实验结果和图表统一整理。
3. 再回写第一章和第二章，使其与最终系统设计和实验结论严格对齐。
4. 最后写摘要、结论与展望。

## 一句总括

这篇论文最合适的写法，不是“比较三种数据结构谁赢了”，而是：

- 围绕低延迟交易场景，设计并实现一个本地 L2 订单簿维护系统；
- 再通过 baseline 与三种 L2 特化实现的统一对比，说明不同设计在当前工程阶段的收益、局限与后续优化方向。
