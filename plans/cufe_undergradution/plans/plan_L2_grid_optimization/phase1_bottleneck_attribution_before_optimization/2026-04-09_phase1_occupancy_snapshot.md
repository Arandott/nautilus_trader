# Phase 1 Occupancy Snapshot

Date: 2026-04-09

## Scope

本文件只回答两件事：

1. 当前 `L2GridBook` 的静态 page 表示到底有多重。
2. 在 authoritative 10m replay 数据集上，page occupancy 到底是什么形状。

采样方法：

- 数据集：`/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`
- limit：`10_000_000` deltas
- replay 采样频率：每 `10_000` deltas 采样一次，总计 `1_000` 个 snapshot
- layout 数据来自 `L2GridBook::diagnostic_layout()`
- 原始输出：`2026-04-09_phase1_diagnostics_report.json`

## Static Layout

### Measured sizes

| Item | Bytes |
| --- | ---: |
| `PriceRaw` | `16` |
| `Price` | `32` |
| `Quantity` | `32` |
| `GridLevel` | `64` |
| `Option<GridLevel>` | `80` |
| `BTreeMap<PageId, GridPage>` header | `24` |
| `SideGrid` | `96` |
| `GridPage` | `5,152` |
| `L2GridBook` | `240` |

### Page body split

`GridPage = 5,152 bytes` 的拆分非常直接：

- `levels: [Option<GridLevel>; 64]` 占 `5,120 bytes`
- page metadata 只占 `32 bytes`

也就是说，当前 `GridPage` 的 `99.4%` 体积都来自固定槽位数组，而不是 bitmap 或计数字段。

### Effective bytes per active level

只看 page body，不算 `BTreeMap` node、自身 allocator 开销和 `L2GridBook` 其他元数据：

| Active slots in one page | Page bytes per active level |
| --- | ---: |
| `1` | `5,152.0` |
| `2` | `2,576.0` |
| `4` | `1,288.0` |
| `8` | `644.0` |
| `16` | `322.0` |
| `32` | `161.0` |
| `64` | `80.5` |

这张表是 phase1 最重要的静态结论之一：如果 replay 下 page 平均只能放 1 个活跃档位，那么 `grid` 结构在 page body 这一层就已经退化成“每个 level 背一个 5KB 容器”。

## Replay Occupancy

### Core result

authoritative replay 的 occupancy 几乎完全退化成：

- `1 populated page = 1 active level`
- `1 active level = 1 active slot`

这不是局部现象，而是采样全程的稳定结果。

### Bid side summary

| Metric | Value |
| --- | ---: |
| avg active pages / sample | `12,212.146` |
| avg active levels / sample | `12,212.146` |
| p50 active pages | `13,639` |
| p95 active pages | `16,187` |
| max active pages | `16,526` |
| avg active slots / populated page | `1.0` |
| p50 active slots / populated page | `1` |
| p95 active slots / populated page | `1` |
| max active slots / page | `1` |
| fraction populated pages with `<= 4` slots | `1.0` |
| fraction populated pages with `<= 8` slots | `1.0` |
| fraction populated pages with `>= 32` slots | `0.0` |

### Ask side summary

| Metric | Value |
| --- | ---: |
| avg active pages / sample | `9,259.297` |
| avg active levels / sample | `9,259.297` |
| p50 active pages | `9,761` |
| p95 active pages | `12,167` |
| max active pages | `12,465` |
| avg active slots / populated page | `1.0` |
| p50 active slots / populated page | `1` |
| p95 active slots / populated page | `1` |
| max active slots / page | `1` |
| fraction populated pages with `<= 4` slots | `1.0` |
| fraction populated pages with `<= 8` slots | `1.0` |
| fraction populated pages with `>= 32` slots | `0.0` |

### Final snapshot

replay 结束时仍然没有出现 page-local density：

- bids：`16,251` active pages，对应 `16,251` active levels
- asks：`12,222` active pages，对应 `12,222` active levels

对应的 occupancy histogram 在 bid / ask 两侧都只有一个非零桶：

- `hist[1] > 0`
- `hist[2..64] = 0`

### Interpretation

phase1 可以明确下结论：

1. 当前 authoritative 数据集并不提供 `L2GridBook` 需要的 contiguous dense pages。
2. 当前 replay 下，grid page 没有兑现“一个 page 吸收多个相邻 tick”的局部性优势。
3. 当前 RSS 异常不是 bitmap 元数据过重，而是固定 page body 在极端稀疏 occupancy 下被放大了。

## Practical Reading

如果把 replay 里的平均 occupancy 代回静态 layout：

- 当前观测平均约等于 `1 active slot / page`
- 那么 page body 的有效成本接近 `5,152 bytes / active level`
- 且这还没有把 `BTreeMap<PageId, GridPage>` 的 node 开销算进去

这足以解释为什么 frozen baseline 里：

- `l2grid` peak RSS 约 `248.9 MB`
- `l2tree` / `l2vec` 都只有约 `31 MB`

## Caveat

phase1 诊断里也记录了 page span 相关数字，但在 `high-precision` raw tick 空间下，span 本身非常大，而且 ask side 的 percentile 会碰到 `u64` 上界。这个指标可以作为“price space 极稀疏”的辅助信号，但不是本阶段的主证据。

主证据其实更简单，也更强：

- populated page 的平均、p50、p95、max occupancy 全都是 `1`

这已经足够支撑 phase1 的密度结论。
