# 第四章 系统实现

## 4.1 实现基础

在第三章完成系统需求分析与总体设计之后，第四章进一步对面向低延迟交易场景的本地 L2 订单簿维护系统进行实现层说明。需要指出的是，本文系统并非脱离既有框架从零构建的独立平台，而是基于 `NautilusTrader` 开源量化交易框架，在其数据模型、订单簿抽象、基准测试入口和真实回放入口之上完成扩展实现。这样的实现起点既保证了 baseline 的工程代表性，也使本文提出的三种特化结构能够直接嵌入现有仓库并接受统一验证。

从代码组织上看，本文系统主要由四部分构成。第一部分是 `crates/model/src/orderbook/` 下的订单簿核心实现，其中 `book.rs`、`ladder.rs`、`level.rs` 构成原生 `OrderBook(BookType::L2_MBP)` 的主要路径，`l2.rs` 定义统一 `L2BookOps` 抽象并实现 `L2TreeBook` 与 baseline 适配，`l2_vec.rs` 与 `l2_grid.rs` 分别实现 `L2VecBook` 和 `L2GridBook`。第二部分是 `crates/model/benches/l2_book_baseline_criterion.rs`，用于组织统一 microbench。第三部分是 `crates/adapters/tardis/bin/l2_baseline.rs`，用于组织真实数据集 replay 与周期查询工作负载。第四部分是 `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py`，用于将多轮 benchmark 与 replay 结果整理为可直接进入论文分析阶段的结构化材料。

为了更清晰地说明第四章的实现范围，本文将主要文件与功能对应关系整理如表 4-1 所示。

表 4-1 系统实现中的主要文件与职责

| 文件路径 | 主要职责 |
| --- | --- |
| `crates/model/src/orderbook/book.rs` | 原生 `OrderBook` 对象及通用 `add/update/delete` 入口 |
| `crates/model/src/orderbook/ladder.rs` | bid/ask 两侧 `BookLadder` 的 level 管理、缓存与删除路径 |
| `crates/model/src/orderbook/l2.rs` | `L2BookOps` 统一接口、`L2TreeBook` 实现与 baseline 适配 |
| `crates/model/src/orderbook/l2_vec.rs` | `L2VecBook` 连续内存实现与诊断辅助逻辑 |
| `crates/model/src/orderbook/l2_grid.rs` | `L2GridBook` 稀疏分页网格实现与最佳价缓存 |
| `crates/model/benches/l2_book_baseline_criterion.rs` | 统一 microbench 入口 |
| `crates/adapters/tardis/bin/l2_baseline.rs` | 真实 replay runner 与周期查询测量入口 |
| `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py` | 多轮运行、结果采集与摘要汇总 |

从实现语言与运行环境看，本文将核心维护路径放在 Rust 层完成。这是因为该部分既需要对内存布局、容器选择和更新路径保持较强控制，也需要与 `NautilusTrader` 现有 Rust 订单簿实现直接衔接。与在脚本层开展原型化比较相比，这种组织方式更适合支撑面向低延迟交易场景的研究问题。与此同时，外围实验编排和结果汇总则由 Python 脚本完成，以便更高效地组织多轮实验、目录结构和摘要文件生成。通过这种分层方式，系统在保留热路径低开销特征的同时，也兼顾了实验闭环的可操作性。

因此，第四章的实现说明将遵循“统一抽象先行、具体结构后述、运行闭环最后补齐”的顺序展开。首先介绍 `L2BookOps` 这一统一接口及公共机制；随后分别说明 baseline、`L2TreeBook`、`L2VecBook` 与 `L2GridBook` 的实现；最后介绍正确性校验、benchmark、真实回放与结果汇总的实现链路。

## 4.2 统一接口与公共机制实现

### 4.2.1 `L2BookOps` 统一抽象

为了使 baseline 与三种特化结构能够在同一系统中被统一驱动和比较，本文在 `crates/model/src/orderbook/l2.rs` 中定义了统一 trait `L2BookOps`。这一抽象并不试图覆盖 `OrderBook` 的全部通用能力，而是仅保留与纯 `L2_MBP` 本地维护和查询直接相关的核心操作。具体而言，`L2BookOps` 包括以下几类能力。

第一类是构造与状态读取能力，包括 `new_l2`、`instrument_id`、`sequence`、`ts_last` 和 `update_count`。这些接口使上层 runner 能够在不知道底层具体结构的前提下统一创建订单簿对象，并读取高水位 sequence、最新事件时间以及累计更新计数等公共状态。

第二类是更新能力，包括 `reset`、`apply_delta_unchecked`、`apply_delta`、`apply_deltas_unchecked` 和 `apply_deltas`。其中，`apply_delta_unchecked` 是热路径核心接口，供 replay runner 和 microbench 在已知输入合法时直接调用；`apply_delta` 和 `apply_deltas` 则在外围补充 instrument 一致性检查，以保证不同运行场景下的安全边界一致。

第三类是查询能力，包括 `best_bid_price`、`best_ask_price`、`best_bid_size`、`best_ask_size`、`top_n_levels` 和 `query_depth_checksum`。其中，`top_n_levels` 负责导出统一的外部 price-size 序列，而 `query_depth_checksum` 则为 benchmark 与 replay 场景提供一种更轻量的查询消费方式。具体做法是：对前若干档 price 与 size 的内部原始值进行累加，形成一个不需要分配额外对象即可被 `black_box` 消费的校验值，从而在不引入额外业务逻辑的前提下稳定测量查询路径。

由此可见，`L2BookOps` 的作用并不只是提供一组统一调用入口，而是将本文的研究对象明确限定为“围绕相同 L2 输入语义展开的状态维护与核心查询问题”。所有具体实现都必须在这组接口内完成构造、更新与查询，上层 benchmark 与 replay 框架也因此能够以统一方式调用 baseline、`L2TreeBook`、`L2VecBook` 和 `L2GridBook`。

### 4.2.2 公共状态推进机制

除了统一的接口形状之外，四种实现还共享一套公共状态推进语义。无论底层结构如何变化，订单簿对象都维护 `sequence`、`ts_last` 和 `update_count` 三个核心字段。每当有新的 delta 被成功吸收后，系统都按照高水位语义更新 sequence 与时间戳，并对累计更新次数执行饱和递增。这样做的目的在于保证不同实现不仅在簿面结果上可比，而且在外围统计上也能保持一致。

在输入合法性方面，`apply_delta` 先检查 `delta.instrument_id` 是否与当前 book 匹配，若不匹配则立即返回错误；`apply_delta_unchecked` 则跳过这一检查，直接进入实现特定的更新路径。这种“两层接口”设计一方面保证了外部入口的健壮性，另一方面也避免在高频 replay 热路径上重复承担相同校验成本。

对于 `OrderSide::NoOrderSide` 这种特殊输入，四种实现基本遵循一致处理方式：若动作为 `Add`，则返回错误；若动作为 `Update/Delete` 且 `order_id` 非零，则按“未知 order_id 更新或删除”跳过处理；若动作为 `Clear`，则允许正常清空。这一处理规则并非本文额外引入，而是与 baseline 已有语义保持对齐，其目的在于保证特化结构不会因为输入边界条件不同而获得额外的性能收益。

### 4.2.3 统一增量处理流程伪代码

为了更清晰地概括 `L2BookOps` 抽象下的公共处理流程，本文将其整理为算法 4-1。

```text
算法4-1 统一 L2 增量处理流程
输入：book, delta, need_validate
输出：更新后的 book 状态

1: if need_validate 且 delta.instrument_id != book.instrument_id then
2:     返回 InstrumentMismatch 错误
3: end if
4: order <- delta.order
5: if order.side == NoOrderSide then
6:     if delta.action == Add then
7:         返回 NoOrderSide 错误
8:     else if delta.action in {Update, Delete} 且 order.order_id != 0 then
9:         直接跳过本条 delta
10:    else if delta.action in {Update, Delete} then
11:        返回 NoOrderSide 错误
12:    end if
13: end if
14: 按 delta.action 进入具体实现的价位维护路径
15: 用高水位规则更新 sequence 与 ts_last
16: update_count 执行饱和递增
17: 返回成功
```

算法 4-1 体现出本文系统实现中的一个重要原则，即“外围校验统一，内部维护分化”。也就是说，instrument 检查、边界条件处理和公共状态推进由统一抽象保证，而真正决定性能差异的部分，则被约束在不同实现的价位维护路径内部。后续四节的实现说明，正是在这一公共骨架之上展开的。

## 4.3 baseline 对照实现

### 4.3.1 原生 `OrderBook(BookType::L2_MBP)` 的接入方式

本文的 baseline 直接采用 `NautilusTrader` 原生 `OrderBook(BookType::L2_MBP)`，并通过 `impl L2BookOps for OrderBook` 的方式接入统一接口，而不是额外构造一个“简化基线”。这样做有两层意义：一方面，baseline 本身就是现有框架中可运行、可复用、可验证的通用工程实现；另一方面，后续三种特化结构也因此能够与真实工程起点而非人为弱化对象进行对照。

从对象结构上看，`OrderBook` 自身维护 `bids` 与 `asks` 两个 `BookLadder`。每个 `BookLadder` 内部同时持有 `levels: BTreeMap<BookPrice, BookLevel>` 和 `cache: HashMap<u64, BookPrice>`。其中，`levels` 负责维持价位有序结构，`cache` 用于从 `order_id` 反查其所在价位。进一步看，每个 `BookLevel` 又维护 `IndexMap<OrderId, BookOrder>` 形式的内部订单容器。因此，baseline 的 L2 路径虽然已经按价位组织，但其更新原语依然是通用订单簿语义下的 `add(order)`、`update(order)` 与 `delete(order)`，而不是纯粹的 `upsert(level)` 与 `delete(level)`。

需要强调的是，这并不意味着 baseline “完全没有 L2 优化”。事实上，baseline 已经具备基于 `BTreeMap` 的价位排序能力，也已经能通过首个价位直接读取 best bid 与 best ask。本文之所以仍将其作为特化对象，不是因为它在渐近复杂度上存在明显问题，而是因为在纯 `L2_MBP` 场景下，它仍然保留了 `synthetic order_id`、`cache`、`BookLevel.orders` 等通用语义残留，这些残留会带来常数级更新开销、额外容器访问与更厚的对象层次。

### 4.3.2 baseline 的 L2 更新路径

在 `OrderBook(BookType::L2_MBP)` 中，每条增量首先经过 `pre_process_order` 处理。对于 `L2_MBP`，该函数会根据价格生成一个稳定的 `synthetic order_id`，其目的是把价位语义映射回通用订单语义，使后续 `BookLadder` 仍能沿用逐订单的更新接口。随后，系统根据买卖方向选择 `bids` 或 `asks` 对应的 `BookLadder`，再进入 `add`、`update` 或 `delete` 路径。

若动作为 `Add`，系统先把 `order_id -> BookPrice` 写入 `cache`，再检查目标价位是否已存在：若已存在，则向该 `BookLevel` 中添加或替换订单；若不存在，则构造新的 `BookLevel` 并插入 `levels`。若动作为 `Update`，系统需要先借助 `cache` 找到旧价位，再判断是否属于原价位内的数量更新，或属于跨价位移动；若价位发生变化，还需要从旧价位删除并重新走一遍添加逻辑。若动作为 `Delete`，系统同样先通过 `cache` 找到对应价位，再在 `BookLevel.orders` 中删除目标订单，必要时删除空价位。

因此，baseline 的 L2 维护路径可以概括为“以价位为外层组织、以订单语义为内部更新原语”的方式。它能够正确处理 `L2_MBP` 数据，但在纯价位维护场景下仍保留了若干额外步骤：先完成价格到 `synthetic order_id` 的映射，再执行 `order_id` 到价位的反查，最后进入 `BookLevel` 内部的订单容器。这正是后续 `L2TreeBook`、`L2VecBook` 和 `L2GridBook` 试图进一步压缩的部分。

### 4.3.3 baseline 核心维护伪代码

```text
算法4-2 baseline 的 L2 价位维护流程
输入：delta
输出：更新后的 baseline 簿面

1: if delta.action == Clear then
2:     清空 bids 和 asks
3:     更新公共状态并返回
4: end if
5: order <- pre_process_order(L2_MBP, delta.order, delta.flags)
6: ladder <- 根据 order.side 选择 bids 或 asks
7: if delta.action == Add then
8:     book_price <- order.to_book_price()
9:     cache[order.order_id] <- book_price
10:    if book_price 已存在于 ladder.levels then
11:        在该 BookLevel 中写入或替换 order
12:    else
13:        创建新的 BookLevel 并插入 levels
14:    end if
15: else if delta.action == Update then
16:    old_price <- cache 中 order.order_id 对应的价位
17:    if old_price 存在 then
18:        若价格未变化，则更新该 BookLevel 中的 order
19:        若价格变化，则先从旧价位删除，再按 Add 路径重插入
20:        若旧价位为空，则删除该价位
21:    else if order.size > 0 then
22:        按 Add 路径处理
23:    end if
24: else if delta.action == Delete then
25:    old_price <- cache 中 order.order_id 对应的价位
26:    若存在，则从对应 BookLevel 删除 order，并在必要时删除空价位
27: end if
28: 更新公共状态
```

### 4.3.4 baseline 查询路径与对照价值

虽然 baseline 的更新路径较为通用，但其查询路径已经相对直接。best bid 与 best ask 可通过各侧 `BookLadder` 的首个价位获得，top-N 查询也可以沿有序价位执行前缀遍历。因此，在后续实验中，baseline 在 best bid/ask 与 top-N 查询上并不必然处于明显劣势。也正因为如此，本文将其定位为“通用语义最完整的工程参考基线”，而不是为了衬托新结构而人为构造的弱基线。

换言之，baseline 在第四章中的意义并不只是“旧实现”，而是后续三种结构的共同参照系。只有先把 baseline 在系统中的真实角色与内部路径交代清楚，后续对专门化收益的解释才具备可信度。

## 4.4 `L2TreeBook` 实现

### 4.4.1 设计思路与数据组织

`L2TreeBook` 定义在 `crates/model/src/orderbook/l2.rs` 中，是本文三种特化结构里最接近 baseline 价位组织方式的一种。它保留了树形有序容器这一点，但将内部表示直接压缩为 `BTreeMap<BookPrice, Quantity>`。也就是说，与 baseline 相比，`L2TreeBook` 去除了 `synthetic order_id`、`cache` 和 `BookLevel.orders` 这三层额外语义，使每个价位直接对应一个聚合后的数量值。

在对象结构上，`L2TreeBook` 仅维护 `instrument_id`、`sequence`、`ts_last`、`update_count` 以及 `bids`、`asks` 两棵树。由于 `BookPrice` 已经内含买卖方向信息，并通过已有比较规则保证买侧按价格从优到劣排序、卖侧按价格从优到劣排序，因此系统仍然可以通过 `iter().next()` 直接得到最优价位。这使得 `L2TreeBook` 在保持查询路径简洁的同时，把更新语义从“订单操作”收敛为“价位操作”。

### 4.4.2 更新与查询实现

在更新层面，`L2TreeBook` 将 `Add` 与 `Update` 统一为价位 `upsert_level` 操作，即直接把给定价位上的数量写入 `BTreeMap`；`Delete` 则直接从对应侧的树中移除指定价位；`Clear` 同时清空两侧树结构。这样的实现路径没有了 baseline 中 `price -> synthetic order_id -> cache -> BookLevel` 的多层跳转，因此更新行为更接近纯 `L2_MBP` 语义本身。

在查询层面，`best_bid_price`、`best_ask_price`、`best_bid_size` 和 `best_ask_size` 都通过 `best_level` 从首个价位直接返回结果；`top_n_levels` 则对相应侧的有序树做前 `depth` 档遍历；`query_depth_checksum` 则在遍历过程中直接对 price 与 quantity 的原始值求和，以减少临时对象分配。

从实现角度看，`L2TreeBook` 的优势在于保留了价位有序树在动态插删上的稳定性，同时通过直接存储价位聚合数量，显著压缩了通用语义残留。由此，该结构在工程上较适合作为默认实时维护方案的候选。不过，第四章在此仅说明实现逻辑本身，具体实验表现留待第五章分析。

### 4.4.3 `L2TreeBook` 核心维护伪代码

```text
算法4-3 `L2TreeBook` 的价位维护流程
输入：delta
输出：更新后的 `L2TreeBook`

1: order <- delta.order
2: if delta.action in {Add, Update} then
3:     levels <- 根据 order.side 选择 bids 或 asks
4:     levels[BookPrice(order.price, order.side)] <- order.size
5: else if delta.action == Delete then
6:     levels <- 根据 order.side 选择 bids 或 asks
7:     从 levels 中删除 BookPrice(order.price, order.side)
8: else if delta.action == Clear then
9:     清空 bids 与 asks
10: end if
11: 更新 sequence、ts_last 与 update_count
```

## 4.5 `L2VecBook` 实现

### 4.5.1 设计思路与连续内存布局

`L2VecBook` 定义在 `crates/model/src/orderbook/l2_vec.rs` 中，其核心目标不是继续强化树结构，而是利用连续内存布局改善 top-k 深度读取与局部盘口扫描的访问局部性。为此，`L2VecBook` 将两侧簿面分别存储为有序 `Vec<Level>`，其中每个 `Level` 仅保存 `price_raw` 与 `size_raw` 两个字段。与 baseline 和 `L2TreeBook` 相比，这一结构不再依赖红黑树或 BTree 节点间跳转，而是把同一侧的活跃价位尽量紧凑地排布在连续内存中。

为了支持从内部原始值恢复外部可比较的 `Price` 与 `Quantity`，`L2VecBook` 额外维护 `price_precision` 和 `size_precision` 两个字段，并在更新过程中用 `observe_precisions` 持续记录已观测到的最大精度。这样做的意义在于，内部更新路径可以始终围绕更轻的原始值展开，而对外查询时再按统一精度恢复为系统其他模块可消费的对象表示。

### 4.5.2 定位、更新与诊断实现

对于 `Vec` 路线来说，最关键的问题不再是如何维护树结构，而是如何在保持买卖两侧有序的前提下，以尽可能低的代价完成插入、更新与删除。`L2VecBook` 的做法是使用 `binary_search_by` 在对应侧的向量中定位目标价位。买侧按照价格降序比较，卖侧按照价格升序比较，因此可以在统一函数 `find_level_index` 中完成双侧定位。

在具体操作上，`Add` 路径会先定位目标价位。若数量非零且该价位已存在，则直接覆盖数量；若数量非零且不存在，则在目标下标处执行插入；若数量为零，则不执行额外操作。`Update` 路径会在命中已存在价位时更新数量，并在数量归零时执行删除；若未命中且新数量非零，则按插入处理；若未命中且数量为零，则同样不执行额外操作。`Delete` 路径则在命中时移除对应下标。由此可见，`L2VecBook` 的主要维护成本不在定位，而在于中部插入和删除时需要搬移后续元素。

为了更清晰地解释这一点，`L2VecBook` 还额外提供了 `probe_delta` 与若干诊断结构，用于记录某条 delta 对应的变更类型、插入位置、搬移层数和搬移字节数。这些诊断信息对后续解释 `L2VecBook` 的性能边界具有重要意义，因为它们能够较为直接地揭示连续布局优势与动态维护成本之间的工程权衡关系。

在查询层面，`L2VecBook` 的 best bid/ask 只需读取每侧向量的首元素，top-N 查询也只需对前若干个连续元素做线性遍历。因此，该结构更适合以连续深度读取为主的场景，例如 top-k 深度扫描、盘口形状提取以及若干依赖局部顺序访问的因子计算。

### 4.5.3 `L2VecBook` 核心维护伪代码

```text
算法4-4 `L2VecBook` 的价位维护流程
输入：delta
输出：更新后的 `L2VecBook`

1: side_levels <- 根据 delta.order.side 选择 bids 或 asks
2: index <- 在 side_levels 中对 delta.order.price 执行二分定位
3: if delta.action == Add then
4:     if delta.order.size == 0 then
5:         不执行额外操作
6:     else if index 命中已存在价位 then
7:         直接覆盖该位置的 size_raw
8:     else
9:         在 index 处插入新 level
10:    end if
11: else if delta.action == Update then
12:    if index 命中已存在价位 then
13:        若数量非零则原地更新，否则删除该位置
14:    else if 数量非零 then
15:        在 index 处插入新 level
16:    else
17:        不执行额外操作
18:    end if
19: else if delta.action == Delete then
20:    若 index 命中，则删除该位置
21: else if delta.action == Clear then
22:    清空 bids 与 asks
23: end if
24: 更新 sequence、ts_last 与 update_count
```

## 4.6 `L2GridBook` 实现

### 4.6.1 设计思路与分页网格组织

`L2GridBook` 定义在 `crates/model/src/orderbook/l2_grid.rs` 中，是本文三条路线里最强调利用价格离散 tick 结构的一种。与前两种实现不同，`L2GridBook` 不再把每个活跃价位都直接放入单个树或单个向量，而是先将原始价格映射为离散 tick，再按固定页大小将这些 tick 分配到若干页中。当前实现中，页大小 `PAGE_SIZE` 为 64，即每个页包含 64 个固定槽位。

具体而言，系统先用原始价格的 `raw` 值作为 tick 表示，再通过 Euclidean division 将 tick 映射为 `(page_id, slot)`。其中，`page_id = tick.div_euclid(PAGE_SIZE)`，`slot = tick.rem_euclid(PAGE_SIZE)`。同一页内部由 `GridPage` 管理，页内维护 `levels: [Option<GridLevel>; PAGE_SIZE]` 和一个 `u64` 占用位图 `occupancy_bitmap`。每一侧再通过 `SideGrid` 维护 `BTreeMap<PageId, GridPage>`，并缓存 `best_page` 与 `best_tick`。这样，系统既能在页级保持有序性，又能在页内利用位图快速定位最优槽位。

### 4.6.2 页内操作与最佳价修复

在页内层面，`GridPage` 的 `upsert` 会把给定槽位标记为占用，并写入相应的 `GridLevel`；`remove` 会清除该槽位并同步修正位图与活跃计数。为了保证页内查询效率，`best_slot` 会根据买卖方向分别使用 `leading_zeros` 或 `trailing_zeros` 在位图上定位最佳槽位。也就是说，对于买侧，最佳槽位是位图中最高有效位对应的位置；对于卖侧，最佳槽位是最低有效位对应的位置。

在页间层面，`SideGrid` 维护 `pages`、`best_page` 和 `best_tick`。当有新价位写入时，系统会判断该 tick 是否优于当前缓存的最佳 tick，若是则直接更新缓存。当删除操作移除了当前最佳价位时，系统不会盲目全局重扫，而是先尝试在同一页内恢复新的最佳槽位；若该页已空或不再有更优槽位，再根据买卖方向向相邻非空页扩展查找。这样的设计使 `L2GridBook` 在某些高密度局部区间内，有机会把“最佳价更新”压缩到页内位图扫描与少量页级跳转上。

在查询方面，`top_n_levels` 通过 `visit_top_levels` 从最佳方向开始遍历页，再在每一页内借助位图顺序访问有效槽位。`query_depth_checksum` 也是在这一遍历过程中直接累加原始值。由此可见，`L2GridBook` 的核心思想并不是简单地“用数组代替树”，而是试图同时利用价格离散性、页级稀疏性和页内位图扫描这三种结构特征。

### 4.6.3 `L2GridBook` 核心维护伪代码

```text
算法4-5 `L2GridBook` 的价位维护流程
输入：delta
输出：更新后的 `L2GridBook`

1: tick <- delta.order.price.raw
2: (page_id, slot) <- 将 tick 映射到页号与槽位
3: side_grid <- 根据 delta.order.side 选择 bids 或 asks
4: if delta.action in {Add, Update} then
5:     if delta.order.size > 0 then
6:         若 page_id 不存在，则创建新页
7:         在该页 slot 位置写入数量，并更新占用位图
8:         若 tick 优于当前 best_tick，则刷新 best_page 与 best_tick
9:     else
10:        删除该价位，并在必要时修复最佳价缓存
11:    end if
12: else if delta.action == Delete then
13:    删除该价位，并在必要时修复最佳价缓存
14: else if delta.action == Clear then
15:    清空 bids 与 asks 及其 best 缓存
16: end if
17: 更新 sequence、ts_last 与 update_count
```

## 4.7 正确性校验实现

对于订单簿维护系统而言，性能比较必须建立在先通过正确性检查的前提之上。基于这一原则，本文在实现阶段就把 baseline 作为统一参考实现，并将所有候选结构的外部状态统一转化为按 side 划分的 price-size 序列进行比较，而不是直接比较内部对象字段。这一点与第三章提出的“查询与校验模块”是一致的。

从当前代码实现看，三种特化结构文件内部都包含与 baseline 的 parity 测试。测试内容至少覆盖以下几项：best bid price、best ask price、best bid size、best ask size、买卖两侧 top-N levels、sequence、`ts_last` 以及 `update_count`。例如，在 `l2.rs`、`l2_vec.rs` 与 `l2_grid.rs` 的测试模块中，都可以看到基于相同 delta 输入同时驱动 baseline 与候选实现，再比较其对外状态是否一致的断言逻辑。

这样的实现方式有两个优点。第一，它保证了 correctness 检查围绕统一外部语义展开，而不会因为内部容器不同导致伪差异。第二，它使每种特化结构在开发过程中都能够较快验证自身是否偏离 baseline 语义，从而为后续 benchmark 和 replay 提供可信前提。进一步看，这种基于统一接口和统一 price-size 导出的比较方法，也为第五章的实验设计奠定了直接基础。

## 4.8 Benchmark 与 Replay 运行实现

### 4.8.1 Criterion microbench 实现

为了刻画不同结构在细粒度路径上的行为差异，本文在 `crates/model/benches/l2_book_baseline_criterion.rs` 中实现了统一的 Criterion 基准测试入口。该文件通过泛型函数 `seeded_book<B: L2BookOps>()` 先为任意实现构造一份相同的初始簿面：买卖两侧各写入固定数量的价位，再在此基础上执行目标操作。这样的设计避免了不同实现因初始状态不同而导致的测试偏差。

当前 microbench 共覆盖五类核心场景：更新已有价位、插入新价位、删除已有价位、best bid/ask 查询和 top-10 查询。前 3 类场景主要面向更新热路径，后 2 类场景主要面向典型读取路径。所有测试项均以 `L2BookOps` 为统一抽象，因此 baseline、`L2TreeBook`、`L2VecBook` 和 `L2GridBook` 能在完全相同的测量框架下被执行。

在具体测量方式上，更新已有价位场景使用固定两个 delta 交替更新同一价位；插入与删除场景则借助 `iter_custom` 手动控制插入-清理与删除-恢复过程，以避免单次测量受到簿面逐渐退化的影响；查询场景通过 `black_box` 消费最优价或深度校验值，防止编译器将整个查询路径优化掉。由此，microbench 所测得的结果能够较好地反映不同结构在局部路径上的真实差异。

### 4.8.2 真实 replay runner 实现

在 microbench 之外，本文还在 `crates/adapters/tardis/bin/l2_baseline.rs` 中实现了统一 replay runner，用于评估不同结构在真实 L2 增量流下的整体表现。该 runner 支持 `parse_only`、`replay_only` 和 `replay_periodic_query` 三种模式，其中后两者用于第五章的主要实验。

该 runner 首先通过 `nautilus_tardis::csv::stream_deltas` 按固定 chunk 大小读取原始数据集，再根据命令行参数选择具体 `book` 类型。对于 replay 模式，runner 内部使用泛型函数 `run_replay<B: L2BookOps>` 驱动任意订单簿实现。也就是说，无论选择 baseline、`L2TreeBook`、`L2VecBook` 还是 `L2GridBook`，其回放逻辑均完全共享，差异只存在于 `apply_delta_unchecked` 的具体实现。

在 `replay_only` 模式下，runner 只负责顺序吸收 delta 并统计整体处理时间；在 `replay_periodic_query` 模式下，runner 则按给定的 `query_interval` 周期性调用 `run_queries`，同时测量查询总时间、平均查询时间和最大查询时间。为了保证查询路径本身能够被稳定执行而不会被优化掉，`run_queries` 会同时消费 best bid/ask 和 `query_depth_checksum` 的结果。除此之外，runner 还会记录总 delta 数、吞吐、累计 query 次数、book 自身 update_count、当前和峰值 RSS、commit id 以及 UTC 时间戳等信息，从而为后续结果汇总提供完整原始材料。

由此可见，真实 replay runner 在系统中的作用并不是单纯提供一个运行入口，而是承担了连接统一输入流、统一订单簿接口和统一指标输出的功能。只有通过这一入口，本文才能将第四章中的结构实现真正置于同一工作负载下接受整体检验。

## 4.9 结果采集与汇总实现

为了把多轮 Criterion 与 replay 结果整理为可直接用于论文分析的材料，本文在 `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py` 中实现了统一结果汇总脚本。该脚本负责解析命令行参数、校验参与比较的 book 集合、创建输出目录，并按预设轮数依次执行 microbench 与 replay runner。

在目录组织上，脚本会自动生成 `raw`、`processed` 和 `summaries` 三类输出目录。`raw` 目录主要保存每次运行的日志和 runner 输出 JSON；`processed` 目录保存从 Criterion 估计文件中抽取出的中间结果；`summaries` 目录则生成适合论文分析与横向比较的摘要文件。通过这样的分层组织，系统可以同时保留原始运行证据和更高层的聚合结果。

在执行逻辑上，脚本既支持多 book、多模式、多 query interval 的批量比较，也支持通过 `repeats`、`limit` 和 `depth` 等参数调整实验规模。更重要的是，脚本不会为某一种结构单独设置特殊路径，而是始终围绕同一 runner 和同一 benchmark 名称组织命令调用。因此，它构成了第四章实现部分的最后一环，即将统一接口和统一运行入口转化为统一结果材料，进而为第五章的实验结果分析提供稳定输入。

通过这一实现链路，本文实际上搭建了一套完整的研究闭环：底层结构负责簿面维护，中间层接口负责统一调用，runner 与 benchmark 负责统一测量，结果汇总脚本负责统一整理。这样，论文中的性能分析便不再停留于零散的单次运行结果，而是建立在可复现、可追踪、可扩展的系统实现基础之上。

## 4.10 本章小结

本章围绕面向低延迟交易场景的本地 L2 订单簿维护系统，说明了系统在 `NautilusTrader` 代码框架中的具体落地方式。首先，本文说明了系统所依托的主要代码位置与文件职责，并指出核心维护路径由 Rust 实现、外围实验编排与结果整理由 Python 脚本完成。随后，本文介绍了统一 `L2BookOps` 接口及其公共状态推进机制，并给出了统一增量处理流程伪代码。

在此基础上，本章分别说明了 baseline、`L2TreeBook`、`L2VecBook` 和 `L2GridBook` 的实现方式。其中，baseline 保留了通用订单簿语义下的 `synthetic order_id`、`cache` 与 `BookLevel.orders` 路径；`L2TreeBook` 将表示压缩为直接的价位树；`L2VecBook` 强调连续内存布局与二分定位；`L2GridBook` 则利用离散 tick、分页组织与位图扫描构造更激进的专门化路径。最后，本文说明了正确性校验、Criterion microbench、真实 replay runner 与结果汇总脚本的实现链路，展示了系统如何由结构实现进一步延伸到完整实验闭环。

综上，第四章完成了从第三章总体设计到可运行系统实现之间的具体展开。下一章将在本章实现基础之上，对统一 benchmark 与真实回放场景下的实验结果进行分析，并进一步讨论 baseline 与三种特化结构各自的工程适用边界。
