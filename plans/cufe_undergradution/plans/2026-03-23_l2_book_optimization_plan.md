# CUFE 本科毕业设计完整计划

日期：2026-03-23

## 1. 项目定位

本课题围绕 `L2_MBP` 订单簿数据的本地持久化与高效维护展开，目标不是重新发明一套底层数据库，而是在保留原始交易所 `delta` 作为 `source of truth` 的前提下，针对 `nautilus_trader` 当前偏通用化的订单簿子系统做 `L2` 专项优化。

核心判断如下：

- 当前 `nautilus_trader` 已支持 `L2_MBP`，但内部仍沿用通用订单簿思路。
- `L2_MBP` 的真实操作对象是 `price level`，不是单笔订单。
- 因此优化重点应放在 `L2Book` 的内部状态表示、更新路径和真实 workload 下的性能收益，而不是优先重写持久化底层编码。

## 2. 研究问题

本课题希望回答三个问题：

1. 在相同原始 `delta` 输入下，面向 `price level` 的 `L2Book` 是否优于当前通用 `OrderBook(L2_MBP)`？
2. 语义层专用化之外，不同底层数据结构是否会继续带来显著收益？
3. 这些收益在真实研究 workload 中是否有意义，而不仅仅体现在微基准上？

## 3. 范围与边界

本阶段明确纳入的内容：

- 复用原始交易所 `delta` 作为输入与落盘对象
- 基于相同输入比较 baseline 与优化版本
- 实现多个 `L2Book` 变体
- 做 profiling、microbench、真实 workload benchmark
- 做正确性校验

本阶段暂不作为主线的内容：

- 周期性 checkpoint
- 仓库内部独立 `replay.rs`
- 全新独立 backend
- 高度复杂的存储引擎功能，如 segment compaction、稀疏索引、多级恢复

恢复能力仍然保留，但优先通过外部脚本或 API 顺序回放原始 `delta` 实现。

## 4. Baseline 与 Proposed 方案

### 4.1 Baseline

以原生 `nautilus_trader` 作为 baseline：

- `Baseline-A`：原生通用订单簿更新路径
- `Baseline-B`：原生持久化/读取路径

实验中最主要对比对象是 `Baseline-A`，因为本课题的核心创新主要在订单簿子系统。

### 4.2 Proposed 方案分层

为了形成循序渐进的研究链，计划实现三个 `L2Book` 版本：

#### `L2TreeBook`

特点：

- 采用 `L2` 专用语义
- 内部操作以 `upsert/delete(price level)` 为核心
- 底层使用有序树结构，例如 `BTreeMap<price, size>`

研究目的：

- 验证“L2 专用语义”本身是否已经能带来收益
- 尽量降低实现风险，作为主实现版本

#### `L2VecBook`

特点：

- 保持 `L2` 专用语义
- 底层使用 `sorted Vec` 或 `Vec + index` 方案

研究目的：

- 进一步研究缓存友好内存布局对回放和查询性能的影响
- 作为中间增强版本

#### `L2GridBook`

特点：

- 保持 `L2` 专用语义
- 利用价格离散 tick 的特征，将 `price` 映射到索引空间
- 底层考虑 tick-indexed array、sparse grid、bitset 辅助定位等思路

研究目的：

- 验证利用市场结构特征是否能进一步逼近极致性能
- 作为高风险、高收益版本

## 5. 预期开销与性能假设

### 5.1 Baseline 预期开销

当前原生 `L2_MBP` 路径的潜在额外开销包括：

- `price -> synthetic order_id` 的哈希转换
- `order_id -> BookPrice` 的额外 `cache` 映射维护
- `BookLevel` 内部仍保存 `IndexMap<OrderId, BookOrder>`
- level 尺寸统计带有“订单级语义残留”
- 更新路径仍是 `add/update/delete(order)`，而不是纯 level 原语

### 5.2 Proposed 性能假设

`L2TreeBook` 预期收益：

- 减少不必要的 order 语义开销
- 降低单条 delta 更新开销
- 降低 replay 总耗时
- 降低内存占用

`L2VecBook` 预期收益：

- 在顺序扫描 `top-N`、连续 replay、特征提取场景下表现更好
- 改善 cache locality

`L2GridBook` 预期收益：

- `quantity_at(price)`、`upsert/delete` 可能接近常数级
- 对稠密价格区间的回放和查询有更强优势

同时也要预期可能出现的负面结果：

- `L2TreeBook` 相对 baseline 只有常数级优化，而非数量级提升
- `L2VecBook` 在高频插入/删除新价位时可能退化
- `L2GridBook` 可能因价格范围管理复杂导致收益不稳定

## 6. Profiling 与验证思路

本课题不采用“先写代码，再看跑分”的方式，而采用“先立性能假设，再用 profiling 验证”的方式。

验证流程如下：

1. 明确 baseline 的潜在开销来源
2. 设计 `L2TreeBook / L2VecBook / L2GridBook`
3. 针对每个版本做 microbench
4. 对热点路径做 profiling
5. 用真实 workload 验证收益是否有意义

需要重点关注的热点：

- 单条 delta 的更新路径
- 重复更新已存在 level 的路径
- 新 level 插入路径
- level 删除路径
- `best bid/ask`
- `top-N`
- 特征提取时的连续查询

## 7. Workload 设计

### 7.1 原子 workload

用于解释“为什么会快”：

- `update_existing_level`
- `insert_new_level`
- `delete_existing_level`
- `best_bid_ask`
- `top_10_query`
- `quantity_at_price`

### 7.2 真实 workload

用于解释“快在哪里有意义”：

#### Workload A：Full-day replay

输入：

- `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

目标：

- 测试一整天原始 `delta` 顺序回放性能

指标：

- 总耗时
- updates/s
- 峰值内存

#### Workload B：Replay + periodic top-N query

目标：

- 模拟“边回放边取特征”的真实研究流程

方案：

- 每处理固定数量 `delta`，查询一次 `best bid/ask` 与 `top-10`
- 查询频率设置梯度，例如每 `1`、`10`、`100`、`1000` 条查询一次

#### Workload C：Replay + feature extraction

目标：

- 模拟量化研究中基于 L2 的实时特征计算

建议特征：

- spread
- midpoint
- top-k imbalance
- microprice
- 指定价位数量

#### Workload D：Windowed reconstruction

目标：

- 模拟本地研究时反复提取某个时间窗数据

方案：

- 选取多个时间段
- 顺序回放到目标窗口
- 比较不同结构在局部重建与特征计算上的性能

## 8. 正确性验证

性能优化之前，先保证结果一致。

正确性校验包括：

- 每条 `delta` 应用后 best bid/ask 一致
- 指定深度 top-N 一致
- 指定 price 的数量一致
- spread、midpoint、一组基础 L2 特征一致
- 全量 replay 结束后最终订单簿状态一致

验证方式：

- 同一份原始 `delta` 同时喂给 baseline 与 proposed
- 在固定步数做抽样比对
- 在关键时间点做全量状态比对

## 9. 工程实现策略

优先采用“并行新增”而不是“直接侵入替换”的方式：

- 保留现有 `OrderBook` 作为 baseline
- 新增 `L2TreeBook / L2VecBook / L2GridBook`
- 外部 benchmark/profiling 脚本驱动同一份 `delta` 输入
- 如有必要，再逐步考虑接入更深层的 cache/engine

这样做的好处是：

- baseline 保留完整
- 变量更干净
- 更适合论文实验
- 降低对现有系统的破坏性

## 10. 阶段推进计划

### 阶段 0：Baseline 建模

- 梳理原生 `L2_MBP` 路径
- 写清楚预期开销
- 建立 benchmark 与 profiling 框架

### 阶段 1：`L2TreeBook`

- 定义 `L2` 专用接口
- 实现 `upsert/delete/query`
- 跑 correctness + microbench + full-day replay

### 阶段 2：`L2VecBook`

- 实现向量化版本
- 重点关注 replay 和 top-N 的收益
- 比较其与 `L2TreeBook` 的 trade-off

### 阶段 3：`L2GridBook`

- 设计价格离散化映射
- 评估稠密/稀疏区间下的收益与复杂度
- 判断是否适合作为论文高级扩展

### 阶段 4：论文整理

- 收敛实验结论
- 提炼“收益来源”
- 写系统设计、实验设计、结果分析与局限性

## 11. 风险与应对

主要风险：

- `L2TreeBook` 相对 baseline 收益不够大
- `L2VecBook` 更新成本不稳定
- `L2GridBook` 实现复杂度过高
- 单一 BTCUSDT 数据集不足以支撑泛化结论

应对策略：

- 将 `L2TreeBook` 作为最小可交付主成果
- `L2VecBook` 与 `L2GridBook` 作为增强层，允许部分完成
- 通过 profiling 解释收益来源，即使收益有限也能形成扎实结论
- 后续补充更多日期或第二个品种做泛化验证

## 12. 预期交付物

- 一份完整的 `L2` 订单簿优化设计文档
- `Baseline / L2TreeBook / L2VecBook / L2GridBook` 对比实现
- benchmark 与 profiling 脚本
- 真实 workload 实验结果
- 正确性验证脚本
- 可直接用于开题和论文写作的结构化材料

## 13. 当前执行建议

接下来最应该做的不是立刻写所有版本，而是先完成以下三件事：

1. 定义 `L2Book` 统一接口
2. 写 baseline 开销假设表
3. 落地 `L2TreeBook` 作为第一版主实现

只要这三件事稳住，后面的 `L2VecBook`、`L2GridBook`、profiling 和真实 workload 都会顺很多。
