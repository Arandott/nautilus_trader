# Chapter 4 Source Notes

## 1. 主要代码锚点

- 统一接口与公共机制：
  - `crates/model/src/orderbook/l2.rs`
- baseline：
  - `crates/model/src/orderbook/book.rs`
  - `crates/model/src/orderbook/ladder.rs`
  - `crates/model/src/orderbook/level.rs`
  - `crates/model/src/orderbook/aggregation.rs`
- `L2TreeBook`：
  - `crates/model/src/orderbook/l2.rs`
- `L2VecBook`：
  - `crates/model/src/orderbook/l2_vec.rs`
- `L2GridBook`：
  - `crates/model/src/orderbook/l2_grid.rs`
- microbench：
  - `crates/model/benches/l2_book_baseline_criterion.rs`
- replay runner：
  - `crates/adapters/tardis/bin/l2_baseline.rs`
- 汇总脚本：
  - `cufe_undergraduate_playground/scripts/measurement/run_l2_book_comparison.py`

## 2. 第四章里要特别守住的表述边界

- 要明确写本文系统基于 `NautilusTrader` 开发，但不要写成“只是在现有系统上做少量修改”。
- baseline 要写成“通用语义最完整的工程参考实现”，不要写成故意构造出来的弱基线。
- 对 baseline 的问题描述应聚焦于 `synthetic order_id`、`cache`、`BookLevel.orders` 和通用更新原语带来的常数级残留开销，不要写成“每个价位里有很多订单所以很慢”。
- `L2TreeBook`、`L2VecBook`、`L2GridBook` 的实现动机都应被正面呈现，不要在第四章提前写成胜负叙事。
- `L2VecBook` 应强调连续布局、二分定位和 shift/memmove 成本之间的平衡。
- `L2GridBook` 应强调 tick 离散化、分页组织和位图扫描，不要把它缩写成“数组实现”。

## 3. 伪代码排版说明

- 当前 `ch4_content.md` 中的算法块使用纯文本伪代码，目的是先把逻辑骨架固定下来。
- 后续并入 Word 总稿时，建议将 `算法4-1` 到 `算法4-5` 转成学校允许的 `Algorithm` 风格排版。
- 这些伪代码不需要完全逐行对应 Rust 代码，更适合保留“输入、关键分支、状态更新、输出”四层。
- 如果版面紧张，可保留：
  - `算法4-1`
  - `算法4-2`
  - `算法4-3`
  - `算法4-4`
  - `算法4-5`
  这五个核心算法即可。

## 4. 后续可能需要微调的点

- `L2TreeBook` 当前实现里，`Add` 和 `Update` 统一走 `upsert_level` 路径，正文不宜过度展开零数量更新语义。
- `L2VecBook` 的 `probe_delta`、`L2VecDeltaProbe` 和布局诊断是很有价值的材料；如果第四章篇幅太长，可以正文轻写，在第五章结果解释时再补。
- `L2GridBook` 当前实现中的 `PAGE_SIZE = 64`、页内 bitmap 扫描、`best_page/best_tick` 修复逻辑都是真实代码细节，可以保留。
- 正确性校验目前更像“统一语义 + parity tests + correctness spec”的组合，而不是一个单独二进制程序；正文写法应保持这一事实边界。

## 5. 与第五章的衔接建议

- 第四章结尾不要提前宣布谁是唯一最优结构。
- 第五章可以沿下面这条线展开：
  - baseline：通用参考
  - `L2TreeBook`：默认实时维护方案
  - `L2VecBook`：因子计算友好结构
  - `L2GridBook`：dense/deep 专项候选

## 6. 结果口径参考

- 最新解释口径：
  - `cufe_undergraduate_playground/thesis/brainstorm/2026-04-10_l2_orderbook_final_benchmark_interpretation_and_thesis_guidance.md`
- 最新 unified compare 目录：
  - `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10`
