# Phase 1: `L2Vec` Shift Cost Attribution And Payload Compaction

日期：2026-04-10

本目录记录 `L2VecBook` 第一轮优化的完整证据链：

- 先用 diagnostics 量化 replay 中的 `Vec` 搬移成本
- 再做一次低风险的 payload compaction
- 最后用真实 replay smoke 和 parity test 验证收益与正确性

核心结论：

- 当前 `L2VecBook` 的 replay 掉速，主因确实是中部插删导致的大规模 `Vec` 搬移
- 原始 `Level` 体积为 `64 bytes`，在 `100k` replay 采样里平均每条 delta 约搬移 `50.8 KB`
- 将 level 存储压缩为 `raw price + raw quantity` 后，`Level` 体积降到 `32 bytes`
- 同一 replay 采样下，平均每条 delta 的搬移字节降到 `25.4 KB`
- 在真实 `10M replay` smoke 中，`l2vec replay_only` 吞吐从旧 authoritative 的 `126391.43 updates/s`
  提升到 `175089.47 updates/s`

主文档：

- `2026-04-10_phase1_l2vec_payload_compaction_memo.md`
