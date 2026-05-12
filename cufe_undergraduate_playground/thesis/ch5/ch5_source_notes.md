# Chapter 5 Source Notes

## Primary result sources

- Benchmark interpretation:
  `cufe_undergraduate_playground/thesis/brainstorm/2026-04-10_l2_orderbook_final_benchmark_interpretation_and_thesis_guidance.md`
- Final summary:
  `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/summaries/comparison_summary.md`
- Processed replay summary:
  `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/processed/runner_summary.json`
- Processed criterion summary:
  `cufe_undergraduate_playground/results/comparisons/all_books_subset_10m_r3_q100_q1000_final_2026-04-10/processed/criterion_estimates.json`

## Figure files

- `figures/criterion_cases.svg`
  - Suggested caption: `图 5-1 Criterion microbench 关键路径对比图`
- `figures/replay_throughput.svg`
  - Suggested caption: `图 5-2 不同工作负载下的 replay 吞吐对比图`
- `figures/query_latency.svg`
  - Suggested caption: `图 5-3 周期查询场景平均查询延迟对比图`
- `figures/peak_rss.svg`
  - Suggested caption: `图 5-4 不同工作负载下的峰值 RSS 对比图`

## Figure generation

- Script:
  `cufe_undergraduate_playground/thesis/ch5/generate_figures.py`
- Recommended command:

```bash
source .venv/bin/activate
python cufe_undergraduate_playground/thesis/ch5/generate_figures.py
```

## Writing guidance

- Keep the current chapter-level positioning:
  - `L2TreeBook`: default real-time maintenance winner
  - `L2VecBook`: factor-friendly / continuous-depth-read structure
  - `L2GridBook`: dense/deep specialist candidate
  - `baseline`: general-purpose reference
- Avoid writing:
  - `L2GridBook` failed
  - `L2VecBook` is unsuitable for real markets
  - `L2TreeBook` is universally optimal for all workloads
- The chapter should remain evidence-first:
  - environment -> correctness premise -> microbench -> replay throughput -> periodic query -> memory -> integrated discussion

## Notes for final Word integration

- The SVG charts can be imported into Word directly, or exported to PNG/PDF if needed.
- The current markdown uses inline image embedding only as a drafting aid; final thesis typesetting should convert them into the school's required figure/caption format.
- `MiB` is used in the current tables because the source data are converted from bytes using `1024^2`. If the school prefers `MB`, unify the unit during final formatting and keep the conversion convention consistent.
