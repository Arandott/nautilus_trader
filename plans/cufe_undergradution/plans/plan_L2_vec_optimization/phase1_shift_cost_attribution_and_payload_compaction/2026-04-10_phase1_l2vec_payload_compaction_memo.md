# Phase 1 Memo: `L2VecBook` Payload Compaction

日期：2026-04-10

## 1. 目标

这一轮不尝试重写 `L2VecBook` 的插删策略，而是先回答一个更窄但更关键的问题：

`L2VecBook` 的 replay 掉速，是否主要来自“每次中部插删要搬移太多字节”？如果是，那么先压缩
`Level` payload，能不能在不改接口语义的前提下拿到一轮确定性收益？

## 2. 诊断结论

新增诊断工具：

- `crates/adapters/tardis/bin/l2_vec_diagnostics.rs`

诊断基于真实数据集：

- `/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz`

压缩前 `100k` replay 采样的关键结论：

- `level_size_bytes = 64`
- `total_shift_events = 43382`
- `avg_shifted_levels_per_shift_event = 1830.48`
- `avg_shifted_bytes_per_delta = 50822.19`
- shift 事件中，`>1024 levels` 的大搬移占 `34247` 次
- 插入位置以 `middle = 23055` 为主，删除位置以 `middle = 18760` 为主

这说明 `L2VecBook` 的问题不是“binary search 太慢”，而是：

- replay 下 book 深度很深
- 中部插删很多
- `Level` 本体又太重

因此，第一轮最合理的动作不是大改结构，而是先压缩 payload。

## 3. 实现修改

修改文件：

- `crates/model/src/orderbook/l2_vec.rs`

核心改动：

1. 把单个 level 从 `Price + Quantity` 改成只存：
   - `price_raw`
   - `size_raw`
2. 在 `L2VecBook` 级别维护：
   - `price_precision`
   - `size_precision`
3. `binary_search`、insert、remove、checksum 都直接基于 raw 值工作
4. `best_bid_ask` / `top_n_levels` 对外返回时，再把 raw 还原成 `Price` / `Quantity`

这样做的前提是本项目的 fixed-point raw 已经按内部固定精度归一化存储，因此比较和排序可以直接
使用 raw，不需要在 `Vec` 内继续背完整对象。

## 4. 压缩后结果

压缩后 `100k` diagnostics：

- 结果文件：
  `cufe_undergraduate_playground/results/comparisons/l2_vec_phase1/diagnostics/l2_vec_diagnostics_limit100k_post_compaction.json`
- `level_size_bytes = 32`
- `total_shifted_levels = 79409671`，与压缩前相同
- `total_shifted_bytes = 2541109472`
- `avg_shifted_bytes_per_delta = 25411.09`

也就是说，这轮优化没有改变“要搬多少个 level”，但把“每次要搬多少字节”基本压到了一半。

## 5. Replay Smoke

对照旧 authoritative 基线：

- 旧基线文件：
  `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000/summaries/all_books_summary.md`
- 旧 `l2vec replay_only = 126391.43 updates/s`
- 旧 `l2vec replay_periodic_query::q100 = 127102.13 updates/s`

本轮 smoke 结果：

- `replay_only`：
  `cufe_undergraduate_playground/results/comparisons/l2_vec_phase1/replay/l2vec_replay_only_10m_post_compaction.json`
  - `updates_per_sec = 175089.47`
  - `peak_resident_bytes = 32157696`
- `replay_periodic_query(q=100)`：
  `cufe_undergraduate_playground/results/comparisons/l2_vec_phase1/replay/l2vec_replay_periodic_query_q100_10m_post_compaction.json`
  - `updates_per_sec = 174812.21`
  - `avg_query_ns = 752`
  - `peak_resident_bytes = 32153600`

按旧 authoritative 口径粗看：

- `replay_only` 吞吐约 `+38.5%`
- `replay_periodic_query(q=100)` 吞吐约 `+37.5%`

## 6. Correctness / Validation

本轮已通过：

- `cargo test -p nautilus-model l2_vec --lib`
- `cargo check -p nautilus-tardis --bin tardis-l2-vec-diagnostics`
- `source .venv/bin/activate && LD_LIBRARY_PATH=... cargo test -p nautilus-tardis --test l2_book_parity --test l2_vec_book_parity`
- `source .venv/bin/activate && LD_LIBRARY_PATH=... cargo run -p nautilus-tardis --bin tardis-l2-baseline -- --mode replay_only --book l2vec --limit 10000000`
- `source .venv/bin/activate && LD_LIBRARY_PATH=... cargo run -p nautilus-tardis --bin tardis-l2-baseline -- --mode replay_periodic_query --book l2vec --query-interval 100 --limit 10000000`

## 7. 当前判断

这一轮已经足够说明两件事：

1. `L2VecBook` 的 replay 弱点并不只是抽象上的 `Vec::insert/remove = O(n)`，而是现实中真的在深簿、
   中部插删、高 payload 的组合下付出了大量字节搬移成本。
2. 即使不改变 `Vec` 结构本身，只做 payload compaction，也能在真实 replay 中拿到非常可观的收益。

但这轮也没有回答所有问题：

- 它是否已经足够接近 `L2TreeBook`？
- 进一步收益更应该来自更轻的 payload，还是来自更激进的插删策略？
- 是否值得为 `L2VecBook` 引入 chunked / gap / tombstone 之类更复杂的结构？

## 8. 建议的下一步

下一轮更值得做的，不是再去优化 query，而是继续围绕 update path：

1. 统计并降低 reallocation / spare capacity 成本
2. 评估是否需要 side-level reserve 策略
3. 如果 replay 仍明显落后 `L2TreeBook`，再考虑更激进的 chunked-vec 方向

在进入更复杂结构之前，这一轮 payload compaction 已经证明：

`L2VecBook` 还有相当真实的工程优化空间，不应被过早定性为“query 强但 replay 注定不行”。
