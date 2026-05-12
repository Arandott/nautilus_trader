# Phase 6 Assessment: 默认策略

日期: 2026-05-09

## 目标

定义默认策略，避免未充分验证前改变生产行为。

## 当前策略

- 默认仍是 `generic`。
- `tree` 只通过显式配置 opt-in。
- `vec` / `grid` 当前不会进入 production facade，传入后 fallback 到 `generic`。
