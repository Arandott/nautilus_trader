# Phase 0 Devlog

- 2026-05-09: 审计原计划与现有 `OrderBook` API。
- 2026-05-09: 确认 `bids()/asks()` 的 `&BookLevel` 返回值是 storage enum 直接替换的主要阻力。
- 2026-05-09: 决定先用可验证的 Tree opt-in facade 接入完整路径，默认仍保持 generic。
