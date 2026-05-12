# Phase 3 Assessment: DataEngine / Cache

日期: 2026-05-09

## 目标

让 managed order book 在 DataEngine / Cache 路径中可选择 L2 backend，同时不改变 cache 存储类型。

## 当前基线

- Cache 仍存 `OrderBook`。
- `BookUpdater` 仍调用 `book.apply_deltas` / `book.apply_depth`。
- `BookSnapshotter` 仍发布 cache 中的同一个 `OrderBook`。
