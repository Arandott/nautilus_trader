# L2 Specialized Book End-to-End Integration Plan

Date: 2026-05-09

## 目标

把当前只在 benchmark/replay runner 中使用的 `L2TreeBook`、`L2VecBook`、`L2GridBook`，接入 NautilusTrader 的完整回测和实盘市场数据路径。接入后，策略、缓存、快照、回测撮合和 Python/Cython API 仍然看到稳定的 `OrderBook` 语义，但 L2_MBP 的内部维护可以选择专用后端。

本方案先把 `L2TreeBook` 作为生产候选后端接入；`L2VecBook` 和 `L2GridBook` 保持 opt-in / shadow / experimental，用来验证 factor 查询和 dense/deep 场景，而不是立即作为默认后端。

## 现状判断

当前特化结构的主入口是 `L2BookOps`，主要服务于：

- `crates/adapters/tardis/bin/l2_baseline.rs`：离线 replay runner 直接泛型调用 `B: L2BookOps`。
- `crates/model/benches/l2_book_baseline_criterion.rs`：Criterion microbench 直接构造四种 book。
- `crates/adapters/tardis/tests/l2_book_parity.rs` 和 `l2_vec_book_parity.rs`：把候选结构和 native `OrderBook(BookType::L2_MBP)` 对齐。

真实端到端路径不是这样调用的。

Rust data engine 路径是：

- `SubscribeBookDeltas` / `SubscribeBookDepth10` 进入 `crates/data/src/engine/mod.rs`。
- `setup_book_updater` 在 managed 模式下创建 `OrderBook::new(instrument_id, book_type)`，并放入 `Cache::add_order_book`。
- `BookUpdater` 在 `crates/data/src/engine/book.rs` 中从 cache 取 `order_book_mut`，对 `OrderBookDeltas` 调 `book.apply_deltas(deltas)`。
- `BookSnapshotter` 从 cache 读同一个 `OrderBook` 并发布快照。

Python/Cython data engine 路径是：

- `nautilus_trader/data/engine.pyx::_setup_order_book` 调 `_create_new_book`。
- `_create_new_book` 构造 `nautilus_trader.model.book.OrderBook`，其底层是 Rust FFI `OrderBook_API(Box<OrderBook>)`。
- `_update_order_book` 从 `Cache.order_book` 取出 `OrderBook`，调用 `order_book.apply(data)`，必要时再 `to_quote_tick()`。
- `_snapshot_order_book` 发布 cache 中的同一个 `OrderBook`。

回测撮合路径还有一条独立 book：

- `nautilus_trader/backtest/engine.pyx` 的 matching engine 在初始化时创建 `_book = OrderBook(instrument_id, book_type)`。
- L2 撮合依赖 `best_bid_price`、`best_ask_price`、`simulate_fills`、`get_quantity_at_level`、`get_all_crossed_levels` 等接口。

因此，当前的问题不是“缺一个 runner”，而是特化结构没有进入 `OrderBook` facade / cache / FFI / matching engine 这些稳定边界。

## 推荐架构

保留外部 `OrderBook` 类型，把特化结构做成 `OrderBook` 的内部 L2 backend。不要让 cache 或策略直接存 `L2TreeBook`，也不要把 `BookType` 扩展成 `L2_TREE` 这类实现细节。`BookType` 表示市场数据语义，backend 表示内部实现。

建议新增内部选择维度：

```rust
pub enum L2BookBackendKind {
    Generic,
    Tree,
    Vec,
    Grid,
}

enum OrderBookStorage {
    Generic {
        bids: BookLadder,
        asks: BookLadder,
    },
    L2Tree(L2TreeBook),
    L2Vec(L2VecBook),
    L2Grid(L2GridBook),
}
```

`OrderBook` 继续暴露原来的方法和 FFI 名称，但内部根据 storage 分发：

- `apply_delta` / `apply_deltas`：L2 backend 走价格档位专用逻辑。
- `apply_depth`：L2 backend 清空后加载 depth10 的有效 price levels。
- `best_bid_price` / `best_ask_price` / size：直接走 backend。
- `bids` / `asks` / `to_deltas`：backend 生成兼容的 `BookLevel` 或 `OrderBookDeltas` 视图。
- `simulate_fills` / `get_quantity_at_level` / `get_all_crossed_levels`：L2 backend 原生实现价格档位扫描，满足回测撮合。
- `filtered_view`、grouping、pretty print 等非热路径：第一阶段可以通过 backend 的 level iterator 构造结果；必要时允许 transient materialization，但不能在 update hot path 维护双份 book。

`L2BookOps` 当前只覆盖 benchmark 所需的窄接口，建议不要直接把它提升为生产 trait。新生产 trait 应覆盖 `OrderBook` 真实接口面，例如：

```rust
trait L2OrderBookCore {
    fn apply_delta_unchecked(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError>;
    fn apply_depth_unchecked(&mut self, depth: &OrderBookDepth10) -> Result<(), BookIntegrityError>;
    fn best_bid_price(&self) -> Option<Price>;
    fn best_ask_price(&self) -> Option<Price>;
    fn best_bid_size(&self) -> Option<Quantity>;
    fn best_ask_size(&self) -> Option<Quantity>;
    fn levels(&self, side: OrderSide, depth: Option<usize>) -> L2LevelIter;
    fn quantity_at_level(&self, price: Price, order_side: OrderSide, size_precision: u8) -> Quantity;
    fn simulate_fills(&self, order: &BookOrder) -> Vec<(Price, Quantity)>;
    fn to_deltas(&self, ts_event: UnixNanos, ts_init: UnixNanos) -> OrderBookDeltas;
}
```

## Backend 选择策略

默认值必须仍是 `Generic`。新增配置只影响 `BookType::L2_MBP`：

- `Generic`：现有行为，默认。
- `Tree`：推荐生产候选，先接入完整路径。
- `Vec`：实验选项，适合 factor/top-k 查询，但不推荐撮合默认。
- `Grid`：实验选项，适合 dense/deep 条件，必须 gated。

配置入口建议分三层：

- 全局默认：`DataEngineConfig.l2_book_backend`，Python 和 Rust config 都加。
- 订阅级覆盖：`SubscribeBookDeltas.params["l2_book_backend"]` / `SubscribeBookSnapshots.params`。
- 回测撮合覆盖：matching engine / exchange config 增加 `l2_book_backend`，只在 instrument 的 `book_type == L2_MBP` 时生效。

命名建议使用 `"generic" | "tree" | "vec" | "grid"`，避免把论文里的 `l2tree` 字符串直接暴露成长期公共 API。

## 关键代码改造点

### 1. Rust model core

目标文件：

- `crates/model/src/orderbook/book.rs`
- `crates/model/src/orderbook/l2.rs`
- `crates/model/src/orderbook/l2_vec.rs`
- `crates/model/src/orderbook/l2_grid.rs`
- `crates/model/src/orderbook/analysis.rs`
- `crates/model/src/ffi/orderbook/book.rs`

工作内容：

- 给 `OrderBook` 增加 backend-aware 构造函数，例如 `OrderBook::new_with_l2_backend(instrument_id, book_type, backend)`.
- 保留 `OrderBook::new`，内部使用 `L2BookBackendKind::Generic`。
- 把 `L2TreeBook` 先补齐生产路径需要的查询接口：depth iterator、exact quantity、crossed levels、simulate fills、to_deltas、apply_depth。
- 将 `OrderBook` 的 L2_MBP 方法按 backend 分发；L1_MBP 和 L3_MBO 仍强制走 generic ladder。
- FFI 增加 `orderbook_new_with_l2_backend`，旧 `orderbook_new` 不变。

### 2. Rust data engine / cache path

目标文件：

- `crates/common/src/cache/mod.rs`
- `crates/data/src/engine/config.rs`
- `crates/data/src/engine/mod.rs`
- `crates/data/src/engine/book.rs`

工作内容：

- cache 仍存 `OrderBook`，不改变 `Cache::add_order_book` 和 `order_book_mut` 的签名。
- `setup_book_updater` 根据 config / command params 创建 backend-aware `OrderBook`。
- `BookUpdater` 不需要知道具体 backend，仍调用 `book.apply_deltas(deltas)`。
- `BookSnapshotter` 不需要知道具体 backend，仍发布 cache 中的 `OrderBook`。

这一步是端到端接入的最小闭环：实盘数据进入 DataEngine 后，cache 里维护的是专用 L2 backend，而不是 runner 里的局部变量。

### 3. Python/Cython wrapper path

目标文件：

- `nautilus_trader/model/book.pyx`
- `nautilus_trader/model/book.pxd`
- `nautilus_trader/core/rust/model.pxd`
- `nautilus_trader/data/config.py`
- `nautilus_trader/data/engine.pyx`
- `nautilus_trader/cache/cache.pyx`

工作内容：

- `OrderBook` Python 类新增可选参数 `l2_backend="generic"`，默认不变。
- `book_type != L2_MBP` 时，如果传入非 generic backend，直接报错或 warning 后回退 generic。
- `_create_new_book` 读取 `DataEngineConfig` 或 subscription params，构造 backend-aware `OrderBook`。
- `_update_order_book`、`_publish_order_book`、`Cache.add_order_book` 不改签名。
- Cython `OrderBook` 的 `apply`、`to_quote_tick`、`to_deltas_c` 等方法继续走同名 FFI。

### 4. 回测 matching engine

目标文件：

- `nautilus_trader/backtest/engine.pyx`
- `nautilus_trader/backtest/config.py` 或对应配置定义
- `tests/unit_tests/backtest/test_matching_engine.py`
- `tests/unit_tests/backtest/test_exchange_l2_mbp.py`

工作内容：

- matching engine 构造 `_book` 时传入 `l2_backend`。
- L2 backend 必须原生支持 `simulate_fills`、`get_quantity_at_level`、`get_all_crossed_levels`。这些接口直接决定 L2 liquidity consumption、queue position 和 passive/marketable order fill 行为。
- 对 `L2TreeBook` 先打开回测选项；`Vec/Grid` 先 shadow 或只允许数据 cache 路径，不建议直接进入撮合默认。

### 5. Adapter local books

若 adapter 内部只是把 venue message 转成 `OrderBookDeltas`，不必优先改。若 adapter 维护本地 `OrderBook` 做 gap repair / snapshot merge / quote extraction，则第二阶段接入：

- Rust examples: `crates/adapters/dydx/src/data.rs`, `crates/adapters/polymarket/src/data.rs`.
- Python examples: `nautilus_trader/adapters/dydx/data.py`, `nautilus_trader/adapters/polymarket/data.py`.

这些 local books 不一定直接暴露给策略，但会影响实盘数据修复路径，需 shadow 验证后再改默认。

## Shadow Mode

正式切换前必须有 shadow mode。建议在 DataEngine 或 BookUpdater 层实现：

- primary book 仍是 generic baseline。
- shadow book 是 `Tree` / `Vec` / `Grid`。
- 每次 `apply_deltas` 后比较：
  - sequence、ts_last、update_count。
  - best bid/ask price/size。
  - top N bid/ask price-size 序列，建议 N=10 和 N=50。
  - depth checksum。
- divergence 日志包含 instrument_id、sequence、delta index、action、side、price、size、baseline topN、candidate topN。

shadow mode 先用于 live sandbox 和 backtest replay，不作为生产输出。

## 验证计划

最小验证不能只跑现有 runner。需要覆盖真实路径：

- Model unit tests：`OrderBook::new_with_l2_backend(..., Tree)` 的 apply/query/to_deltas/simulate_fills 行为与 generic 对齐。
- FFI/Cython tests：Python `OrderBook(..., l2_backend="tree")` 的 apply/bids/asks/best/to_quote_tick/to_deltas 行为对齐。
- Rust DataEngine tests：managed `SubscribeBookDeltas` 后 cache 中的 book 使用指定 backend，`BookUpdater` 能更新，`BookSnapshotter` 能发布。
- Python DataEngine tests：`SubscribeOrderBook(managed=True)` 后 `_update_order_book` 走指定 backend，cache API 不变。
- Backtest tests：L2_MBP matching engine 在 `tree` backend 下通过现有 L2 exchange/matching tests。
- Replay parity：继续用 Tardis 数据做 10M deltas topN parity。
- Shadow live/sandbox：Binance futures 或 Tardis streaming 路径跑 shadow，无 divergence 后再考虑 opt-in。
- Performance gate：对比 full backtest wall time、DataEngine replay wall time、query latency、peak RSS。

## 分阶段落地

### Phase 0: 行为冻结

- 冻结当前 generic `OrderBook(L2_MBP)` 的外部行为作为 oracle。
- 把现有 correctness spec 扩展到 production API：`to_deltas`、`to_quote_tick`、`simulate_fills`、`get_quantity_at_level`、`get_all_crossed_levels`。
- 明确 unsupported 范围：L2 backend 不承诺 L3 per-order time priority。

### Phase 1: Rust core facade

- 新增 `L2BookBackendKind` 和 `OrderBook::new_with_l2_backend`。
- 先只接 `Tree` backend。
- 补齐 `L2TreeBook` 的 production query surface。
- 通过 model-level parity tests。

### Phase 2: FFI 和 Python OrderBook

- 增加 `orderbook_new_with_l2_backend`。
- Python/Cython `OrderBook` 增加可选 backend 参数。
- 通过 Python model tests。

### Phase 3: DataEngine / Cache 接入

- Rust 和 Python DataEngine 都可从 config/params 选择 backend。
- cache 类型保持不变。
- BookUpdater/Snapshotter 路径不改调用点，只由 `OrderBook` 内部分发。

### Phase 4: 回测撮合接入

- matching engine 构造 `_book` 时使用指定 backend。
- 完整跑 L2_MBP 回测撮合测试，重点看 liquidity consumption 和 queue position。
- 第一阶段只开放 `tree`。

### Phase 5: Shadow 和实盘 opt-in

- 开启 shadow mode，先在 replay 和 sandbox 做 divergence 检测。
- `tree` 无 divergence 后允许配置 opt-in。
- `vec/grid` 保持实验 backend，限制在数据路径或 benchmark 场景。

### Phase 6: 默认策略

- 短期：默认仍 `generic`。
- 中期：如果 `tree` 在 full backtest/live shadow 中稳定，允许部分 venue/instrument 默认 `tree`。
- 不建议把 `vec` 或 `grid` 做全局默认；它们的最终定位更像 factor 查询结构和 dense/deep 特化结构。

## 主要风险

- `OrderBook` 当前直接持有 `bids: BookLadder` / `asks: BookLadder`，很多内部方法直接访问字段。改成 storage enum 会牵动较大，需要小步分发。
- FFI `OrderBook_API(Box<OrderBook>)` 现在只包装一个具体 Rust struct。保持 facade 不变可以降低 Python/Cython 改动面。
- 回测撮合依赖的接口比 benchmark 多得多，不能只实现 best/topN。
- `to_deltas` 和 snapshot replay 必须保留 flags、sequence、timestamp 语义，否则历史请求和 buffered deltas 会出错。
- `NoOrderSide`、unknown order_id update/delete 的跳过语义必须与 baseline 完全一致。

## 推荐 review 结论

工程上最稳妥的路线是：不要把特化结构直接塞进 cache，也不要让策略感知新类型；把 `OrderBook` 改造成稳定 facade，在内部为 L2_MBP 选择 backend。先把 `L2TreeBook` 接入完整路径并 shadow 验证，`L2VecBook` 和 `L2GridBook` 暂时作为实验后端保留。这样既能摆脱 toy model，也不会一次性破坏 NautilusTrader 已有的 Python、Rust、回测和实盘接口。
