# Workload Specification

日期：2026-03-23

## 1. 目标

本文档定义后续所有 baseline 与 proposed 版本共享的 workload。

设计原则：

- 同一份原始 `delta` 输入
- 同一套指标
- 既测原子操作，也测真实研究流程
- workload 要能解释收益“为什么有用”

## 2. 数据集

### 2.1 主数据集

当前主数据集为：

- `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

当前已知字段：

- `exchange`
- `symbol`
- `timestamp`
- `local_timestamp`
- `is_snapshot`
- `side`
- `price`
- `amount`

### 2.2 数据集角色

这份数据优先用于：

- Phase 0 baseline replay
- 第一版 microbench 输入模式校准
- 第一版真实 workload

后续扩展数据集用于：

- 跨日期稳定性
- 不同波动状态
- 第二品种泛化验证

## 3. 实现与脚本放置规则

需要明确一件事：

- Rust 生产实现和 Rust benchmark 源码，优先放在对应 crate 下，例如 `crates/model/benches/`
- `cufe_undergraduate_playground/` 主要放运行脚本、配置、结果处理和分析材料

因此建议分工如下：

- Rust microbench 源码：
  - `crates/model/benches/`
- 实验 runner / 配置 / 汇总脚本：
  - `cufe_undergraduate_playground/experiments/`
  - `cufe_undergraduate_playground/scripts/`
- 结果输出：
  - `cufe_undergraduate_playground/results/`

当前仓库已有一个可参考的 benchmark 文件：

- `crates/model/benches/book_iai.rs`

## 4. 测量指标

所有 workload 尽量统一产出以下指标：

- 总耗时
- updates/s
- 单操作平均耗时
- p50 / p95 / p99 延迟（若工具支持）
- 峰值内存
- 结果文件大小
- profiling 热点占比

对于 query-heavy workload，额外记录：

- 每次查询平均耗时
- replay-only 相比 replay+query 的额外开销比例

## 5. Microbench 规格

## 5.1 `update_existing_level`

目标：

- 测试“更新已存在价位”的热路径

定义：

- 预先构造一个包含若干 bid/ask level 的已热身 book
- 重复对已存在 price 应用更新
- baseline 通过 `OrderBook::apply_delta` 或等价路径执行

预期观察：

- `synthetic order_id`
- `cache.get/cache.remove`
- `level.update`

这是 `L2TreeBook` 最应当赢下来的基准之一。

## 5.2 `insert_new_level`

目标：

- 测试“插入新价位”的路径

定义：

- 预先构造一个 book
- 插入当前不存在的新 price level

预期观察：

- `BTreeMap` 插入成本
- `cache.insert`
- `BookLevel::from_order`

## 5.3 `delete_existing_level`

目标：

- 测试“删除已有价位”的路径

定义：

- 对已存在 level 执行删除
- baseline 需要经过 `cache` 找回 price，再删除 level 内部 order

预期观察：

- `cache` 查找与删除
- `level.remove_by_id`
- 空 level 清理

## 5.4 `best_bid_ask`

目标：

- 测试最佳价查询

定义：

- 在已经热身的 book 上重复调用 best bid / best ask API

预期观察：

- baseline 已经较优
- 这项更像“保底指标”，不是主收益来源

## 5.5 `top_10_query`

目标：

- 测试 top-N 查询与遍历

定义：

- 在热身 book 上重复提取 bid/ask 前 10 档

预期观察：

- baseline 与 `L2TreeBook` 差距可能不大
- `L2VecBook` 更有机会在这项上获益

## 5.6 可选 microbench

后续可扩展：

- `quantity_at_price`
- `apply_deltas_batch`
- `feature_step`

## 6. 真实 workload 规格

## 6.1 Workload A: Full-day replay

目标：

- 测试一整天原始 `delta` 顺序回放性能

输入：

- 主数据集全量

执行方式：

- 读取原始 L2 数据
- 转为统一 delta 流
- 顺序喂给 baseline 或 proposed book

输出指标：

- 总耗时
- updates/s
- 峰值内存
- 错误数量

这是最重要的真实 workload。

## 6.2 Workload B: Replay + periodic top-N query

目标：

- 模拟“边回放边取特征”的常见研究流程

定义：

- replay 过程中按固定间隔执行：
  - `best bid/ask`
  - `top-10` bid/ask

建议查询频率：

- 每 `1` 条
- 每 `10` 条
- 每 `100` 条
- 每 `1000` 条

输出指标：

- 总耗时
- 更新吞吐
- 查询平均耗时
- 相比 replay-only 的额外开销比例

## 6.3 Workload C: Replay + feature extraction

目标：

- 模拟量化研究中的 L2 特征提取

第一批建议特征：

- spread
- midpoint
- top-5 imbalance
- microprice
- 指定价位数量

输出指标：

- 总耗时
- 特征步频
- 每个特征批次平均耗时

## 6.4 Workload D: Windowed reconstruction

目标：

- 模拟本地研究中反复提取局部时间窗

定义：

- 选定多个时间窗口
- 重放到目标窗口并运行相同查询 / 特征逻辑

这一项可以晚于前 3 项实现。

## 7. 运行规则

为保证可复现性，建议统一遵守：

- 固定 build profile
- 固定输入文件路径
- 固定 warmup 次数与测量次数
- 同一 workload 至少重复多次取统计值
- 结果记录 commit id、命令、机器信息

Phase 0 推荐最小规则：

- microbench：至少 `5` 次有效测量
- real workload：至少 `3` 次独立运行

## 8. 输出文件约定

建议输出到：

- raw:
  - `cufe_undergraduate_playground/results/baseline/raw/`
- processed:
  - `cufe_undergraduate_playground/results/baseline/processed/`
- summary:
  - `cufe_undergraduate_playground/results/baseline/summaries/`

命名建议：

- `baseline_full_replay_YYYYMMDD.json`
- `baseline_periodic_query_q100.json`
- `baseline_microbench_update_existing_level.json`

后续 proposed 版本按相同模式替换前缀：

- `l2tree_*`
- `l2vec_*`
- `l2grid_*`

## 9. Phase 0 的最小集合

Phase 0 不需要一次性把所有 workload 都跑齐。

最小必须集合：

- `update_existing_level`
- `insert_new_level`
- `delete_existing_level`
- `best_bid_ask`
- `top_10_query`
- `Full-day replay`
- `Replay + periodic top-N query`

这组 workload 已足以支持：

- baseline 建模
- 初始 profiling
- `L2TreeBook` 第一轮验证
