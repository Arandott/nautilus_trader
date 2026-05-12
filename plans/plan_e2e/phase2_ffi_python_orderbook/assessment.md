# Phase 2 Assessment: FFI 和 Python OrderBook

日期: 2026-05-09

## 目标

让 Python/Cython `OrderBook` 能选择 L2 backend，同时保持默认行为不变。

## 当前基线

- Rust FFI 原来只有 `orderbook_new(instrument_id, book_type)`。
- Cython `OrderBook.__init__` 原来只接收 `instrument_id` 和 `book_type`。
