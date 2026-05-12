# Phase 1 Devlog

- 2026-05-09: 新增 `L2BookBackendKind`，默认值为 `Generic`。
- 2026-05-09: `OrderBook::new` 保持旧行为，新增 `new_with_l2_backend`。
- 2026-05-09: Tree backend 支持 production 查询，但当前仍保留 generic ladder 兼容视图。
- 2026-05-09: `Vec` / `Grid` 没有开放到 facade，避免把未补齐的结构误作为生产后端。
