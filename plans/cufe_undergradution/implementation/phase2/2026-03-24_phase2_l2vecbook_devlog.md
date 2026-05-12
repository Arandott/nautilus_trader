# Phase 2 Devlog: `L2VecBook`

日期：2026-03-24

## 1. 本阶段目标

实现一个真正的 Rust-only `L2VecBook`，用于和 baseline `OrderBook(BookType::L2_MBP)` 以及
`L2TreeBook` 做后续 workload 对比。

本阶段关注点是：

- 保持 `L2BookOps` 接口不变
- 使用连续内存的 price-level 布局
- 在正确性上与 baseline 保持一致
- 不改动 Python / FFI / workload 定义 / 持久化路径

## 2. 实现摘要

实现文件：

- `crates/model/src/orderbook/l2_vec.rs`

新增测试：

- `crates/adapters/tardis/tests/l2_vec_book_parity.rs`

核心数据结构：

- `bids: Vec<(Price, Quantity)>`
- `asks: Vec<(Price, Quantity)>`

排序约束：

- `bids` 按 price 降序
- `asks` 按 price 升序

查找与更新策略：

- 使用 `binary_search_by` 按 side 做有序定位
- `Add` 对应 level upsert
- `Update` 对应 level upsert
- `Delete` 删除精确 `(side, price)` level
- `Clear` 清空两侧

## 3. 关键实现选择

### 3.1 为什么直接用 `Vec<(Price, Quantity)>`

这一版优先验证 contiguous layout 是否能在 query-heavy 和 replay-heavy workload
中体现 locality 优势，因此先不引入额外索引结构。

这样做的好处是：

- 头部 level 访问非常直接，`best_bid_ask` 成本低
- `top_n_levels` 和 checksum 查询天然顺序扫描，cache 友好
- 实现简单，便于先把 correctness 和 benchmark harness 跑通

代价也很明确：

- 插入新价位和删除已有价位都需要搬移尾部元素
- 深盘口、且中间价位频繁变化时，性能可能退化

### 3.2 元数据策略

`sequence`、`ts_last`、`update_count` 复用了 `L2TreeBook` 的策略：

- 对乱序 `sequence` / `ts_event` 记录 warning
- `sequence` 取 high-water mark
- `ts_last` 取 high-water mark
- `update_count` 每次应用 delta 都递增

这样可以保证 benchmark / replay 输出口径与现有实验保持一致。

### 3.3 语义对齐

为与当前 baseline 和 `L2TreeBook` 保持一致，本实现遵循以下语义：

- 每个 `(side, price)` 最多保留一个 level
- `Update` 对缺失价位执行 upsert
- 删除缺失 level 为 no-op
- `NoOrderSide` 的处理沿用 `L2TreeBook`

## 4. 测试与验证

已通过的验证：

- `cargo test -p nautilus-model l2_vec_book --lib`
- `cargo test -p nautilus-tardis --test l2_book_parity --test l2_vec_book_parity`
- `cargo check -p nautilus-model --lib`
- `cargo check -p nautilus-model --bench l2_book_baseline_criterion`

单元测试覆盖了：

- 插入后 bid/ask 顺序保持正确
- 更新已有 level
- `Update` 缺失价位时 upsert
- 删除 head / middle / tail
- `Clear` 清空两侧
- synthetic sequence 下与 baseline parity

Tardis 小样本验证：

- 复用了现有 sample CSV replay 路径
- `L2VecBook` 最佳价、最佳量、top-10、元数据均与 baseline 保持一致

## 5. 目前观察

从实现角度看，`L2VecBook` 的优势更可能出现在：

- 高频 `best bid / ask` 查询
- `top_n_levels`
- 盘口深度不大、且结构相对稳定的 replay

它的弱点更可能出现在：

- 频繁插入新价位
- 频繁删除已有价位
- 深盘口中部发生大量结构变动

这些目前还是实现层判断，真实性能结论需要后续 workload 和 benchmark 结果支持。

## 6. 剩余风险

- 当前已证明 correctness，但还没有记录完整 workload 性能结果
- 若后续真实数据集中出现大量 mid-book 插删，`Vec` 搬移成本可能成为瓶颈
- `nautilus-tardis` 测试在本环境运行时需要显式提供 `libpython3.13` 的动态库路径，这是环境问题，不是 `L2VecBook` 逻辑问题

## 7. 结论

Phase 2 已完成一个可运行、可验证、可接入现有 benchmark / replay harness 的
`L2VecBook` 第一版实现。

这一版的价值在于：

- 形成了 baseline / tree / vec 的统一 correctness 对比面
- 后续可以直接进入 workload 对比
- 如果性能不理想，也能基于当前实现明确定位瓶颈是否来自 `Vec` 插删搬移
