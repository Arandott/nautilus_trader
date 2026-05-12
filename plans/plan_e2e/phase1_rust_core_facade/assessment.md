# Phase 1 Assessment: Rust Core Facade

日期: 2026-05-09

## 目标

在 Rust model core 中新增 L2 backend 选择维度，并先接入 `L2TreeBook`。

## 当前实现形态

- 新增 `L2BookBackendKind`:
  - `Generic`
  - `Tree`
  - `Vec`
  - `Grid`
- 新增 `OrderBook::new_with_l2_backend(...)`。
- `Tree` 后端在 `L2_MBP` 上可 opt-in。
- `Vec` / `Grid` 仍保留为实验值，当前通过 facade fallback 到 generic。

## 工程折中

当前没有一次性把 `OrderBook` 改成纯 `OrderBookStorage` enum。为了保持既有 `bids()/asks()` 借用 API 和 FFI 兼容，Tree opt-in book 会同步维护 generic ladder 兼容视图。
