# Phase 5 Assessment: Shadow 和实盘 Opt-in

日期: 2026-05-09

## 目标

在正式切换默认前，提供 primary/shadow 对照路径。

## 当前实现范围

- Rust DataEngine `BookUpdater` 支持 shadow book。
- Shadow book 不写入 cache，不发布给策略，只在每次 update 后比较并记录 divergence。
- Python DataEngine 尚未实现 shadow book；Python 路径当前支持直接 opt-in backend。

## 比较字段

- `sequence`
- `ts_last`
- `update_count`
- best bid price/size
- best ask price/size
- top10 bids
- top10 asks
