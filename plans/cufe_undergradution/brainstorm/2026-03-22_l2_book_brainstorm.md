# CUFE 本科毕业设计 Brainstorm 记录

日期：2026-03-22

## 目标背景

当前毕业设计目标是围绕 L2 订单簿数据做一个本地持久化系统，初始想法是基于 `nautilus_trader` 现有实现做优化。核心判断是：`nautilus_trader` 当前订单簿子系统可以处理 L2，但它的设计更偏向通用化，并没有把 `L2_MBP` 的特性单独拿出来做专项优化。

## 对当前系统的观察

- 当前订单簿实现是通用型的，一套结构服务 `L1/L2/L3`。
- `L2_MBP` 在现有实现里本质上仍然走通用订单簿路径，只是把 price 映射成 synthetic `order_id`。
- `DataEngine` 已经有基于 deltas/depth 驱动 book 更新、并按 interval 发 snapshot 的机制。
- 持久化层已经支持 `order_book_deltas` 和 `order_book_depths`，但更像“已有数据类型的通用落盘”，而不是“面向 L2 高效恢复/查询”的本地存储设计。

这意味着优化空间是真实存在的，尤其适合从 L2 专用数据结构和持久化方式两个角度切入。

## 讨论过的几个方向

### 方向 1：L2 专用内存 CRUD 算法

把当前通用 `OrderBook` 替换或旁路成一个面向 `L2_MBP` 的 level-based 结构。操作对象不是单笔订单，而是 `price level`。核心操作包括：

- `Create`: 新价位出现
- `Read`: best bid/ask、top-N、某时刻书状态
- `Update`: 价位 size/count 更新
- `Delete`: 数量归零后删除价位
- 附加：`Clear / Snapshot Load / Replay`

这个方向最贴近“L2 特化优化”，也是最有算法味道的一条线。

### 方向 2：写优化的本地持久化格式

最开始考虑过单独设计面向 L2 的 append-only delta log，而不是沿用通用对象序列化思路。可以考虑：

- 只保留 L2 必要字段
- side/action/flags 压缩
- price/amount 用 fixed-point 整数表示
- 按 instrument/day 分段

后续讨论后的收敛判断是：

- 实盘场景下，本地落盘的首要对象仍应是交易所原始 delta
- 原始 delta 更适合作为 `source of truth`
- 因此“重新设计一套全新底层存储编码格式”不一定是第一优先级
- 如果后面确实需要做 L2 专用 schema，也可以直接在 `crates/persistence/src/backend/catalog.rs` 上扩展支持，而不必单独重写一个 backend

这个方向仍然可做，但更适合作为“在现有持久化框架上做 L2 适配/增强”，而不是当前阶段的主贡献点。

### 方向 3：checkpoint + recovery

最开始考虑过做周期性 checkpoint，再配合增量回放实现快速恢复。后来收敛出的判断是：

- `checkpoint` 不是必须的
- `recovery` 作为能力可以保留，但不一定要做成独立内部模块

也就是说，可以不做周期性 checkpoint；如果需要恢复/重建，可以由外部实验脚本或 API 顺序读取 delta 并驱动 `L2Book`，不一定非要在仓库内部单独落一个 `replay.rs`。

## 当前最认可的主线

目前最合适的主线是：

### 主线 A：L2 专用 CRUD + 本地日志持久化 + 顺序重建

这条线的特点是：

- 重点放在 L2 专用数据结构和增量维护算法上
- 保留“本地持久化系统”的基本闭环，但不强行把 scope 拉大到 checkpoint/random-access 恢复
- 输入数据尽量保持为原始交易所 delta，把订单簿优化和存储编码问题分开

当前判断：

- `checkpoint` 可以先不做
- 不需要专门实现一个内部 `replay.rs`
- 恢复/重建能力可以通过外部脚本或 API 顺序回放原始 delta 完成
- 这样论文不会退化成“只是做了个 logger”，同时也避免 scope 过度膨胀

## Baseline 的选择

目前认为最合理的 baseline 就是原生 `nautilus_trader`。

但为了实验表达更清晰，建议拆成两层：

- `Baseline A`: 原生通用订单簿更新路径
- `Baseline B`: 原生持久化/回放路径

我们的方法则是：

- `Proposed`: 面向 `L2_MBP` 的专用数据结构，在相同原始 delta 输入下优化更新、查询和重建过程

此外，后续可以再做两组消融：

- 去掉专用 L2 结构，只保留原生通用 book
- 保留专用 L2 结构，但不额外扩展持久化 schema

这样更容易说明性能收益究竟来自哪里。

## 实验数据选择

当前讨论中已经确认这份数据很适合作为主实验数据：

- `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

已观察到的信息：

- 压缩后约 898MB，体量足够做性能实验
- 字段包含：
  - `exchange`
  - `symbol`
  - `timestamp`
  - `local_timestamp`
  - `is_snapshot`
  - `side`
  - `price`
  - `amount`

当前判断：

- 这份数据非常适合作为主案例数据集
- 但不建议作为唯一数据集
- 后续最好再补不同日期、不同市场状态、以及可能的第二个品种做泛化验证

## 当前建议的最小可行系统

如果按当前主线推进，一个比较稳的 MVP 可以是：

1. `L2Book`
   - bid/ask 各自维护 `price -> size`
   - 支持 `upsert / delete / query_top_n / best_bid_ask`

2. `L2DeltaLog`
   - 先直接复用原始交易所 delta 的落盘思路
   - 如有必要，再在 `catalog.rs` 上补 L2 专用 schema 支持

3. `External Replay / Evaluation Script`
   - 通过外部脚本或 API 顺序读取原始 delta
   - 驱动 `L2Book` 完成重建与验证
   - 不强制要求仓库内置独立 `ReplayEngine`

4. `Evaluator`
   - 和原生 `nautilus_trader` 对比吞吐、内存、重建时间、正确性

## 当前共识

- 主线 A 最适合当前毕业设计
- `checkpoint` 可以不作为第一阶段目标
- `recovery` 作为实验能力可以保留，但不必先做成仓库内部独立模块
- baseline 直接选原生 `nautilus_trader` 很合理
- 当前 BTCUSDT 的 L2 数据足够做主实验，但后续应补充更多测试集
- 原始交易所 delta 更适合作为本地持久化的 `source of truth`
- 持久化层优先复用现有思路；若需要支持新 schema，可直接扩展 `catalog.rs`
- 论文主贡献应优先放在 `L2Book` 的 CRUD/更新路径优化，而不是重新设计底层存储编码

## 后续待聊的话题

- L2 专用数据结构具体选型
- L2Book 应该暴露哪些核心接口
- 是否需要在 `catalog.rs` 上补最小 L2 schema 扩展
- 正确性校验指标怎么定
- 实验指标和论文结构怎么写
