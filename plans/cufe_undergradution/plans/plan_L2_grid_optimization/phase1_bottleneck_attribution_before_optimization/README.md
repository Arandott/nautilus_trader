# Phase 1 Outputs

Date: 2026-04-09

本目录保存 `L2GridBook` phase1 的归因产物。

- `2026-04-09_phase1_bottleneck_memo.md`
  - phase1 主结论文档
  - 回答内存主因、性能主因、结构性问题与实现性问题的边界
- `2026-04-09_phase1_occupancy_snapshot.md`
  - 静态 layout 核算
  - authoritative replay 数据集下的 page occupancy / sparsity 采样
- `2026-04-09_phase1_optimization_shortlist.md`
  - 候选优化项的 keep / drop 排序
  - 给出 expected upside / risk / validation cost
- `2026-04-09_phase1_diagnostics_report.json`
  - 原始诊断输出
  - 包含 `size_of` layout、10m replay occupancy 采样、深度 query probe

本阶段使用的核心执行命令：

```bash
source .venv/bin/activate && \
LD_LIBRARY_PATH=/home/ubuntu/.local/share/uv/python/cpython-3.13.9-linux-x86_64-gnu/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
cargo run -p nautilus-tardis --bin tardis-l2-grid-diagnostics -- \
  --dataset /home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz \
  --limit 10000000 \
  --sample-every 10000 \
  --query-levels-per-side 1024 \
  --query-depths 10,100,500,1000 \
  --query-iterations 100000 \
  --output plans/cufe_undergradution/plans/plan_L2_grid_optimization/phase1_bottleneck_attribution_before_optimization/2026-04-09_phase1_diagnostics_report.json
```

附带验证：

```bash
cargo test -p nautilus-model l2_grid --lib
cargo check -p nautilus-tardis --bin tardis-l2-grid-diagnostics
```
