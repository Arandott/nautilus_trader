# Phase 4 Devlog

- 2026-05-09: 回测配置入口放在 venue 层，因为 matching engine 是按 venue/instrument 创建。
- 2026-05-09: 第一阶段只推荐 `tree`。`vec` / `grid` 可传入但会 fallback 到 generic。
- 2026-05-09: 尚未运行完整 L2_MBP 回测套件；本轮已完成 Cython 编译检查。
