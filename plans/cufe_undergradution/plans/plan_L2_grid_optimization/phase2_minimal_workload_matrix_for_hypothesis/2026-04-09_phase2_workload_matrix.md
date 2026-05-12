# Phase 2 Workload Matrix

Date: 2026-04-09

## 目标

Phase 2 的目标是冻结一套足够小、但足够回答 hypothesis 的 workload matrix。

这里要验证的核心 hypothesis 不是：

- `L2GridBook` 还能不能再快一点

而是：

- `L2GridBook` 是否真的更适合更深、更大、且 page 更稠密的 L2 order book workload

## 输入依据

本阶段的 matrix 设计基于三类输入：

- 任务 prompt 对 Phase 2 的明确要求
- Phase 0 对 authoritative baseline 的冻结
- Phase 1 对 occupancy 的定量结论

其中最关键的 Phase 1 结论是：

- 当前 authoritative replay 下，`L2GridBook` 的 page occupancy 基本稳定退化为 `1 populated page = 1 active level`
- 因此，如果不设计真正 dense contiguous pages 的 workload，就很难公平判断 `grid` 是否存在主场

## 设计原则

### 1. 先保留真实世界控制组

即使当前真实 replay 对 `grid` 不友好，也不能把它拿掉。否则后续所有“grid 优势”都可能只是脱离现实约束的结果。

### 2. 一次只让一个关键变量发生变化

这套 matrix 的目标不是大而全，而是可归因。

所以优先只控制这些变量：

- 真实 vs synthetic
- shallow query vs deep query
- dense pages vs sparse pages

### 3. dense / sparse synthetic 必须成对出现

如果只做 dense synthetic，而不做同深度、同 mix 的 sparse 对照，那么即使 `grid` 赢了，也无法判断赢点到底来自：

- density 本身
- synthetic 更简单
- query 更重

### 4. family 数量上限先固定为 4

Phase 2 默认只保留 `4` 组 canonical workload family。

只有在后续出现“结论翻转”或“当前 workload 无法回答问题”时，才允许扩矩阵。

## Canonical Matrix

| ID | 类型 | 要回答的问题 | 主要入口状态 | 主要判读指标 |
| --- | --- | --- | --- | --- |
| `real_shallow_control` | real replay | 当前真实、稀疏、浅查询控制组下，`grid` 的负面结论是否仍然成立 | `现有入口可跑` | `updates_per_sec`、`peak_resident_bytes` |
| `real_deep_query_sparse_replay` | real replay | 在同一份真实稀疏 order book 上，仅把 query 变深，是否会改善 `grid` 相对排名 | `现有入口可跑` | `avg_query_ns`、`max_query_ns`、`updates_per_sec` |
| `synthetic_dense_contiguous_home_court` | synthetic | 当 pages 真的稠密且深度足够大时，`grid` 是否出现主场优势 | `Phase 3 需新增入口` | `deep-query mean ns`、`updates_per_sec`、`peak_resident_bytes`、occupancy |
| `synthetic_sparse_page_control` | synthetic | 如果保持同样的深度和 mix、但强制 pages 稀疏，`grid` 的优势是否消失 | `Phase 3 需新增入口` | `deep-query mean ns`、`updates_per_sec`、`peak_resident_bytes`、occupancy |

## Family 1: `real_shallow_control`

### 这个 workload 在验证什么

它是整个 matrix 的现实控制组，用来回答：

- 当前真实世界下的负结论是否依然存在
- 后续任何 synthetic 正信号，是否只是偏离现实约束后的结果

### 主要假设

这不是 `grid` 的主场。它的作用不是证明 `grid` 赢，而是防止 cherry-pick。

### 主运行配置

- 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- mode：`replay_only`
- books：`baseline`、`l2tree`、`l2vec`、`l2grid`
- limit：`10_000_000`
- depth：`10`

### 运行入口

现有 runner：

- `crates/adapters/tardis/bin/l2_baseline.rs`

命令模板：

```bash
source .venv/bin/activate && \
LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
cargo run -p nautilus-tardis --bin tardis-l2-baseline -- \
  --dataset /home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz \
  --mode replay_only \
  --book <baseline|l2tree|l2vec|l2grid> \
  --depth 10 \
  --limit 10000000 \
  --output cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_shallow_control_btcusdt_10m/<book>.json
```

### 主要指标

- `updates_per_sec`
- `peak_resident_bytes`
- `book_update_count`

### 判读方式

如果这个 workload 上 `l2grid` 仍明显落后于 `l2tree`，这不构成新信息，但它会继续作为所有后续结论的现实锚点。

## Family 2: `real_deep_query_sparse_replay`

### 这个 workload 在验证什么

它用来隔离一个问题：

- 如果保持真实 replay 和真实 sparse pages 不变，只把 query 变深，`grid` 的相对排名会不会改善

### 主要假设

如果 `grid` 的潜在优势主要来自 deep query，而不是 dense pages，那么它至少应该在这个 family 里缩小与 `l2tree` 的差距。

如果这个 family 仍然没有出现信号，说明“deep query alone” 不足以拯救当前实现。

### 主运行配置

- 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- mode：`replay_periodic_query`
- books：`baseline`、`l2tree`、`l2vec`、`l2grid`
- limit：`10_000_000`
- 主 depth：`500`
- 主 query interval：`1000`

### 有边界的变体

这个 family 允许的变体只有：

- depth：`100`
- depth：`1000`

只有当 `depth=500, query_interval=1000` 下，`query_elapsed_ns / elapsed_ns` 对所有 book 都低于 `10%` 时，才允许把 `query_interval` 从 `1000` 进一步压到 `100`。

除此之外，Phase 2 不允许继续扩 real replay 参数。

### 运行入口

现有 runner：

- `crates/adapters/tardis/bin/l2_baseline.rs`

主命令模板：

```bash
source .venv/bin/activate && \
LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
cargo run -p nautilus-tardis --bin tardis-l2-baseline -- \
  --dataset /home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz \
  --mode replay_periodic_query \
  --book <baseline|l2tree|l2vec|l2grid> \
  --depth 500 \
  --query-interval 1000 \
  --limit 10000000 \
  --output cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/real_deep_query_sparse_replay_btcusdt_10m/depth500_q1000/<book>.json
```

### 主要指标

- `avg_query_ns`
- `max_query_ns`
- `updates_per_sec`
- `peak_resident_bytes`

### 判读方式

这个 family 的目标不是要求 `grid` 立刻赢，而是看：

- 它与 `l2tree` 的 query 差距是否明显缩小
- 这种缩小是否需要以明显恶化 throughput 或 RSS 为代价

如果这里只有“略好一点的 query”，但 replay / RSS 继续很差，那么这不是足够强的正信号。

## Family 3: `synthetic_dense_contiguous_home_court`

### 这个 workload 在验证什么

它是为 `grid` 设计的公平主场测试：

- 深度更大
- 相邻 tick 连续
- populated pages 应该真正稠密
- query 也要足够深，才能让 page-local traversal 有意义

### 主要假设

如果 `grid` 这条路线真的有价值，最先出现正信号的地方就应该是这里，而不是当前的真实 sparse replay。

### 目标配置

- active levels per side：`1024`
- price pattern：`dense_contiguous`
- tick step：`1`
- total operations：`2_000_000`
- mix：`update_existing=60%`、`insert=20%`、`delete=20%`
- query mode：periodic deep query
- 主 query depth：`500`
- 有边界变体 depth：`100`、`1000`
- 主 query interval：`100`

### 有效性约束

这个 workload 只有在下面两个条件同时满足时，才算“dense synthetic 有效”：

- `p50 active slots / populated page >= 16`
- `fraction populated pages with >= 32 active slots >= 0.50`

如果达不到这两个条件，就不允许把它当成 dense-case 证据引用。

### 运行入口

当前仓库还没有现成入口能表达这组 workload。

Phase 3 需要新增一个 synthetic runner。推荐入口名：

- `crates/adapters/tardis/bin/l2_synthetic_matrix.rs`
- 对应 bin 名：`tardis-l2-synthetic-matrix`

推荐命令模板：

```bash
source .venv/bin/activate && \
LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
cargo run -p nautilus-tardis --bin tardis-l2-synthetic-matrix -- \
  --book <baseline|l2tree|l2vec|l2grid> \
  --levels-per-side 1024 \
  --price-pattern dense_contiguous \
  --tick-step 1 \
  --operations 2000000 \
  --update-ratio 60 \
  --insert-ratio 20 \
  --delete-ratio 20 \
  --query-depth 500 \
  --query-interval 100 \
  --output cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_dense_contiguous_home_court_1024lvl/depth500_q100/<book>.json
```

### 主要指标

- `deep-query mean ns`
- `updates_per_sec`
- `peak_resident_bytes`
- occupancy distribution

### 判读方式

这是判断 `grid` 是否存在“真实主场”的第一证据位。

如果 `grid` 在这里依然没有出现可复现优势，那么路线本身就需要被认真质疑。

## Family 4: `synthetic_sparse_page_control`

### 这个 workload 在验证什么

它是 Family 3 的严格对照组。

除了 page density 之外，其他关键维度都尽量保持一致，只把 price distribution 改成强稀疏，观察 `grid` 的优势是否随之消失。

### 主要假设

如果 `grid` 在 dense synthetic 上有改善，但在这个 sparse control 上没有改善，那么可以更有把握地说：

- 正信号来自 density，而不是来自 synthetic 更简单

### 目标配置

- active levels per side：`1024`
- price pattern：`sparse_jump`
- tick step：`64`
- total operations：`2_000_000`
- mix：`update_existing=60%`、`insert=20%`、`delete=20%`
- query mode：periodic deep query
- 主 query depth：`500`
- 有边界变体 depth：`100`、`1000`
- 主 query interval：`100`

### 有效性约束

这个 workload 只有在下面条件满足时，才算“sparse control 有效”：

- `p95 active slots / populated page <= 4`
- `p50 active slots / populated page <= 1`

如果这个 sparse control 没有把 occupancy 压低，就失去了对照意义。

### 运行入口

和 Family 3 一样，需要在 Phase 3 新增 synthetic runner。

推荐命令模板：

```bash
source .venv/bin/activate && \
LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
cargo run -p nautilus-tardis --bin tardis-l2-synthetic-matrix -- \
  --book <baseline|l2tree|l2vec|l2grid> \
  --levels-per-side 1024 \
  --price-pattern sparse_jump \
  --tick-step 64 \
  --operations 2000000 \
  --update-ratio 60 \
  --insert-ratio 20 \
  --delete-ratio 20 \
  --query-depth 500 \
  --query-interval 100 \
  --output cufe_undergraduate_playground/results/comparisons/l2_grid_phase2/synthetic_sparse_page_control_1024lvl/depth500_q100/<book>.json
```

### 主要指标

- `deep-query mean ns`
- `updates_per_sec`
- `peak_resident_bytes`
- occupancy distribution

### 判读方式

Family 3 和 Family 4 必须配对看。

只有当：

- dense case 出现正信号
- sparse control 没有同样的正信号

才可以说 `grid` 的优势更可能来自 density。

## 结果目录命名规则

Phase 2 冻结的结果根目录是：

- `cufe_undergraduate_playground/results/comparisons/l2_grid_phase2`

每个 family 使用一个固定目录名：

- `real_shallow_control_btcusdt_10m`
- `real_deep_query_sparse_replay_btcusdt_10m`
- `synthetic_dense_contiguous_home_court_1024lvl`
- `synthetic_sparse_page_control_1024lvl`

family 目录下再按主参数拆子目录，例如：

- `depth500_q1000`
- `depth1000_q100`

单个结果文件统一命名为：

- `<book>.json`

其中 `<book>` 只允许：

- `baseline`
- `l2tree`
- `l2vec`
- `l2grid`

## 扩矩阵规则

Phase 2 明确禁止无边界扩矩阵。

只有出现下面情况，才允许新增 workload 或新增参数：

1. `real_deep_query_sparse_replay` 在 `depth=500, q=1000` 下 query 占比过低。
   - 这时只允许增加 `q=100`，不允许再新增别的 real replay 组合。

2. `synthetic_dense_contiguous_home_court` 没达到 dense validity threshold。
   - 这时允许只围绕 density 校准生成规则，不允许同时新增第二套 synthetic family。

3. `synthetic_dense_contiguous_home_court` 与 `synthetic_sparse_page_control` 出现明确 ranking flip。
   - 这时允许追加一个更大 active depth，例如 `2048`，用于确认信号是否随规模增强。

除上述三种情况外，Phase 2 默认不加新 family。

## Phase 2 Exit Criteria

本阶段退出条件定义为：

1. canonical workload family 已冻结为 `4` 组，而不是继续扩张
2. 每组 workload 都写清了“要回答的问题”和“主要假设”
3. 每组 workload 都写清了运行入口状态
4. 每组 workload 都写清了主要参数和结果目录命名方式
5. 扩矩阵触发条件已经写清，后续不能凭感觉继续加 case

## Exit Decision

上述条件已经满足，所以 Phase 2 可以结束。

更具体地说：

- `real_shallow_control` 已明确保留，作为现实控制组
- `real_deep_query_sparse_replay` 已明确保留，作为“deep query alone” 检验
- `synthetic_dense_contiguous_home_court` 与 `synthetic_sparse_page_control` 已明确成对保留，用来验证 density 假设
- family 数量已经被压到 `4`，没有出现大矩阵失控

## 对下一阶段的含义

Phase 3 不应该直接开始做大量结构优化。

更合理的顺序是：

1. 先把 Family 1 和 Family 2 用现有 runner 跑起来
2. 再补 Family 3 和 Family 4 所需的 synthetic runner
3. 在四组 canonical workloads 能跑通之后，再决定哪些优化值得真正进入代码实现

如果跳过这一步，直接开始改 `PAGE_SIZE` 或 `best repair`，很容易又回到“在错误 workload 上抠常数”的路径。
