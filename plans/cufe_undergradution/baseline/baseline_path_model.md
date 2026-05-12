# Baseline Path Model

日期：2026-03-23

## 1. 目标

本文档用于回答一个最基础的问题：原生 `nautilus_trader` 的 `L2_MBP` 路径到底是怎样工作的。

这份模型是后续性能假设、benchmark 设计和优化实现的依据。

## 2. 输入对象

### 2.1 单条输入

`L2` 更新在模型层的标准输入对象是 `OrderBookDelta`，定义于：

- `crates/model/src/data/delta.rs:42`

核心字段包括：

- `instrument_id`
- `action`
- `order`
- `flags`
- `sequence`
- `ts_event`
- `ts_init`

### 2.2 批量输入

运行时更常见的入口是 `OrderBookDeltas`，定义于：

- `crates/model/src/data/deltas.rs:41`

它本质上是一个 `Vec<OrderBookDelta>` 外加批次级元数据。

## 3. 运行时入口

数据引擎侧的订单簿更新入口在：

- `crates/data/src/engine/book.rs:68`

`BookUpdater::handle(&OrderBookDeltas)` 的行为是：

1. 从 cache 取出对应 `instrument_id` 的 `OrderBook`
2. 调用 `book.apply_deltas(deltas)`

这意味着 baseline 的真实运行入口不是单条 `add/update/delete` API，而是：

`OrderBookDeltas -> BookUpdater -> OrderBook::apply_deltas`

## 4. OrderBook 层路径

`OrderBook` 定义于：

- `crates/model/src/orderbook/book.rs:55`

它同时服务 `L1_MBP`、`L2_MBP` 和 `L3_MBO`，内部持有：

- `bids: BookLadder`
- `asks: BookLadder`

对应代码位置：

- `crates/model/src/orderbook/book.rs:66`
- `crates/model/src/orderbook/book.rs:67`

### 4.1 批量应用

`apply_deltas` 位于：

- `crates/model/src/orderbook/book.rs:353`

其逻辑非常直接：

1. 校验 `instrument_id`
2. 遍历 `deltas.deltas`
3. 逐条调用 `apply_delta_unchecked`

### 4.2 单条应用

`apply_delta_unchecked` 位于：

- `crates/model/src/orderbook/book.rs:301`

它的主要职责是：

1. 处理 `NoOrderSide` 的 side resolution
2. 读取 `action / flags / sequence / ts_event`
3. 按 `Add / Update / Delete / Clear` 分发到 `self.add/update/delete/clear`

## 5. L2_MBP 的关键预处理

真正把 `L2_MBP` 变成当前内部表示的地方在：

- `crates/model/src/orderbook/aggregation.rs:66`

这里的 `pre_process_order(book_type, order, flags)` 会：

- `L1_MBP`：把 `order_id` 改成 side
- `L2_MBP`：把 `price` 通过 `price_to_order_id` 映射成 synthetic `order_id`
- `L3_MBO`：保留原始逐笔语义，只有特定 flag 情况才做转换

相关代码位置：

- `price_to_order_id`: `crates/model/src/orderbook/aggregation.rs:48`
- `price_based_order_id`: `crates/model/src/orderbook/aggregation.rs:55`
- `pre_process_order`: `crates/model/src/orderbook/aggregation.rs:66`

## 6. Ladder 与 Level 内部结构

### 6.1 Ladder

`BookLadder` 定义于：

- `crates/model/src/orderbook/ladder.rs:117`

关键字段：

- `levels: BTreeMap<BookPrice, BookLevel>`
- `cache: HashMap<u64, BookPrice>`

对应代码：

- `crates/model/src/orderbook/ladder.rs:120`
- `crates/model/src/orderbook/ladder.rs:121`

### 6.2 Price 排序规则

`BookPrice` 的排序是 side-aware 的：

- 买侧按价格降序
- 卖侧按价格升序

对应实现：

- `crates/model/src/orderbook/ladder.rs:74`

这也是当前 best bid / best ask 可以直接从 `BTreeMap` 首元素取得的原因。

### 6.3 Level

`BookLevel` 定义于：

- `crates/model/src/orderbook/level.rs:39`

关键字段不是一个简单的 `size`，而是：

- `orders: IndexMap<OrderId, BookOrder>`

对应代码：

- `crates/model/src/orderbook/level.rs:41`

## 7. L2_MBP 在当前实现里的真实语义

这里有一个非常重要的事实：

虽然外部输入是 `L2` 的 price-level delta，但内部并没有变成真正的 `price -> size` 结构，而是：

`price -> synthetic order_id -> BookOrder`

不过，由于 `L2_MBP` 会把同一 price 映射到同一个 synthetic `order_id`，在正常 L2 工作负载下，一个价位通常只会对应一个 synthetic order。

因此，当前 baseline 可以理解成：

- 外层已经是按价位排序的 `BTreeMap`
- 但每个 level 内部仍然保留 order 容器和 order 语义

这也意味着后续优化更可能带来：

- 常数级路径简化
- 内存和容器开销下降
- cache locality 改善

而不是一开始就出现数量级复杂度变化。

## 8. 更新路径细节

### 8.1 Add

`BookLadder::add` 位于：

- `crates/model/src/orderbook/ladder.rs:167`

核心动作：

1. 计算 `book_price`
2. 写入 `cache.insert(order_id, book_price)`
3. 在 `levels` 中查找 price level
4. 若存在则 `level.add(order)`，否则新建 `BookLevel`

### 8.2 Update

`BookLadder::update` 位于：

- `crates/model/src/orderbook/ladder.rs:264`

核心动作：

1. 先通过 `cache.get(order_id)` 找旧 price
2. 找到对应 `level`
3. 若价格不变，调用 `level.update(order)`
4. 若价格变化，先删旧 level 中的 order，再重新 `add`

### 8.3 Delete

`BookLadder::delete` / `remove_order` 位于：

- `crates/model/src/orderbook/ladder.rs:332`
- `crates/model/src/orderbook/ladder.rs:337`

核心动作：

1. 通过 `cache.get(order_id)` 找 price
2. 找到对应 `level`
3. 从 `cache` 删除
4. 从 `level.orders` 删除
5. 若该 level 为空，则从 `levels` 中删除整个价位

## 9. 查询路径

### 9.1 Top-N level

`OrderBook::bids/asks` 位于：

- `crates/model/src/orderbook/book.rs:561`
- `crates/model/src/orderbook/book.rs:566`

它们直接对 `BTreeMap.values()` 做 `take(depth)`。

### 9.2 Best bid / ask

`BookLadder::top` 位于：

- `crates/model/src/orderbook/ladder.rs:448`

`OrderBook::best_bid_price / best_ask_price` 位于：

- `crates/model/src/orderbook/book.rs:819`
- `crates/model/src/orderbook/book.rs:825`

这条路径已经比较短：

`BTreeMap.iter().next() -> BookLevel -> price`

### 9.3 Level size

`BookLevel::size / size_raw / size_decimal` 位于：

- `crates/model/src/orderbook/level.rs:101`
- `crates/model/src/orderbook/level.rs:107`
- `crates/model/src/orderbook/level.rs:113`

它们会对 `orders.values()` 做求和。不过对当前 `L2_MBP` 来说，正常情况下每个价位往往只有一个 synthetic order，因此这里更像“容器与间接层成本”，而不是“大量逐单求和成本”。

## 10. 与论文优化方向的关系

从 baseline 路径看，最值得优化的不是：

- `BTreeMap` 外层排序本身
- best bid / ask 获取方式

而是这些更贴近 L2 专用化的点：

- 去掉 `price -> synthetic order_id`
- 去掉 `order_id -> BookPrice` 的 `cache`
- 去掉 `BookLevel.orders: IndexMap<...>`
- 把内部原语从 `add/update/delete(order)` 收敛成 `upsert/delete(level)`

因此，后续 `L2TreeBook / L2VecBook / L2GridBook` 的真正比较对象是：

“同样吃原始 `OrderBookDelta`，但内部是否仍然保留这层通用 order 语义”。
