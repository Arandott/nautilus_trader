# Phase 2 Devlog

- 2026-05-09: 选择 FFI 参数 `u8`，避免把新 Rust enum 暴露为 C ABI 长期承诺。
- 2026-05-09: Python API 使用稳定字符串: `generic`、`tree`、`vec`、`grid`。
- 2026-05-09: `vec` / `grid` 会被 Rust facade fallback 到 generic。
