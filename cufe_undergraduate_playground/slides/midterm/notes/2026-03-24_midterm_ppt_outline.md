# Midterm PPT Outline

This draft is the working outline for the undergraduate thesis midterm defense
deck. It mixes slide structure, talking points, and figure planning.

## Deck Positioning

The deck should answer four questions clearly:

- Why is the topic worth doing?
- What concrete overheads are we targeting?
- What have we already built and verified?
- Why do the current results matter for research now and live trading later?

Recommended deck length: 10 to 12 slides.

## Slide 1. Title

Title:

- L2 Order Book Local Persistence and Specialized Order Book Optimization Based on NautilusTrader

Content:

- student name
- supervisor
- school and major
- date

Figure plan:

- Optional light background only
- Put image on the full slide background with low opacity

Asset:

- `assets/00_cover_bg.png`

Prompt for Gemini:
`minimal academic background for a thesis defense cover, abstract limit order book, blue-gray palette, clean lines, subtle market microstructure feeling, no text, no logo, professional beamer slide background`

## Slide 2. Background and Motivation

Core message:

- L2 order book data is large, high-frequency, and expensive to replay locally.
- Efficient local persistence and reconstruction are important for quantitative research.
- There is still a lack of mature open-source L2-specialized implementations validated with systematic workloads.

Suggested bullets:

- L2 deltas arrive at high frequency and accumulate into very large local datasets.
- Research workflows repeatedly require replay, query, and factor extraction from the same data.
- Existing open-source systems usually emphasize generality, while L2 has its own structure and optimization opportunities.

Figure plan:

- One concept figure on the right side

Asset:

- `assets/01_l2_research_motivation.png`

Prompt for Gemini:
`academic infographic of L2 limit order book research workflow, exchange delta stream flowing into local storage, replay engine, feature extraction, backtesting, clean vector style, white background, blue and dark teal accents, no text`

## Slide 3. Problem Definition and Research Goal

Core message:

- We focus on `L2 MBP` order books and optimize the local maintenance and replay path.
- The current phase already improves research efficiency.
- The longer-term goal is to connect the optimized L2 path to more realistic live trading workflows.

Suggested bullets:

- Input: raw exchange L2 delta stream
- Current target: improve local replay, query, and research efficiency
- Long-term target: reuse the optimized L2 engine in a more realistic live path

Figure plan:

- Scope diagram

Asset:

- `assets/02_problem_scope.png`

Prompt for Gemini:
`clean system diagram of L2 order book optimization scope, raw exchange deltas, local persistence, specialized L2 book, replay queries, future live trading integration, flat academic style, white background, no text`

## Slide 4. Baseline System and Overhead Sources

Core message:

- `nautilus_trader` is our baseline and integration carrier.
- The baseline is valuable, but its L2 path still carries overhead from more general order book abstractions.

Suggested bullets:

- Baseline path is built on a generic order book design
- For L2, we identified extra overheads such as synthetic order semantics and container indirection
- This leads to a clear optimization question: which overheads can be removed without breaking correctness?

Figure plan:

- No Gemini concept figure needed
- Use a short baseline path block and an overhead table on the same page

## Slide 5. Research Method: Overhead to Evidence

Core message:

- Every design choice is driven by an expected overhead reduction.
- Every expected gain must be checked against its trade-off and verified with workloads.

Suggested bullets:

- Step 1: identify overhead
- Step 2: choose a data structure to reduce it
- Step 3: state the expected trade-off
- Step 4: validate with microbench and replay workloads

Suggested table:

- columns: `Design`, `Target overhead`, `Trade-off`, `Evidence`

Figure plan:

- Small methodology figure above or beside the table

Asset:

- `assets/04_overhead_method.png`

Prompt for Gemini:
`research methodology diagram, overhead identification leads to data structure design, trade-off analysis, benchmark profiling, workload validation, clean academic vector diagram, white background, no text`

## Slide 6. Technical Roadmap

Core message:

- The project follows a progressive optimization route instead of a single ad hoc redesign.

Suggested bullets:

- `Baseline`: generic L2 path in NautilusTrader
- `L2TreeBook`: remove L2-unnecessary abstractions while keeping ordered tree semantics
- `L2VecBook`: improve locality and top-N queries with contiguous storage
- `L2GridBook`: exploit tick discreteness with a grid-like structure

Figure plan:

- One horizontal roadmap across the slide

Asset:

- `assets/05_technical_roadmap.png`

Prompt for Gemini:
`horizontal technical roadmap for L2 order book optimization, baseline generic book to tree book to vector book to grid book, each stage more specialized, clean academic infographic, white background, teal and navy palette, no text`

## Slide 7. Phase 1: L2TreeBook

Core message:

- `L2TreeBook` validates that L2-specialized semantics alone already have clear value.

Suggested structure:

- Target overhead:
  - synthetic order semantics
  - per-level order container overhead
  - extra cache maintenance
- Trade-off:
  - still keeps tree structure, so it is not the most aggressive layout
- Result:
  - stable replay and update improvement over baseline

Figure plan:

- Left: `L2TreeBook` diagram
- Right: one small result box with the key percentage gains

Asset:

- `assets/06_l2treebook_diagram.png`

Prompt for Gemini:
`technical illustration of L2TreeBook, bid side and ask side stored as ordered price-level trees, direct price to size mapping, no per-order storage, clean academic vector diagram, white background, no text`

Data figure to generate locally:

- `assets/06_l2tree_vs_baseline_highlight.png`
- Content: small bar chart of replay throughput and peak RSS, baseline vs l2tree

## Slide 8. Phase 2: L2VecBook

Core message:

- `L2VecBook` improves query locality but pays for insertion and deletion shifts.

Suggested structure:

- Target overhead:
  - scattered memory access during top-N and best-price queries
- Trade-off:
  - inserting or deleting a middle level shifts later elements
- Result:
  - strong query microbench
  - weak replay performance under real delta streams

Figure plan:

- Left: `L2VecBook` diagram
- Right: one contrast box showing "query strong / replay weak"

Asset:

- `assets/07_l2vecbook_diagram.png`

Prompt for Gemini:
`technical illustration of L2VecBook, sorted contiguous arrays for bid and ask price levels, fast top-N reads but insert delete shifts elements, clean academic vector diagram, white background, no text`

Data figure to generate locally:

- `assets/07_l2vec_tradeoff_chart.png`
- Content: side-by-side chart of `top_10_query` vs `replay_only`

## Slide 9. Phase 3: L2GridBook

Core message:

- `L2GridBook` uses price discreteness to reduce part of the search and update overhead.
- The new chunked sparse-grid prototype is more faithful to the grid idea, but under the current dataset it exposes serious sparsity and page-management costs.

Suggested structure:

- Target overhead:
  - remaining tree-comparison overhead after `L2TreeBook`
- Trade-off:
  - page allocation, bitmap maintenance, and best-pointer repair
- Result:
  - replay throughput falls back near baseline level
  - peak RSS becomes much larger than `L2TreeBook`
  - this is still useful because it reveals the real cost of sparse page fragmentation

Figure plan:

- Left: `L2GridBook` diagram
- Right: short result note

Asset:

- `assets/08_l2gridbook_diagram.png`

Prompt for Gemini:
`technical illustration of L2GridBook, tick-indexed sparse grid for bid and ask levels, highlighted best pointer and sparse active ticks, clean academic vector diagram, white background, no text`

Data figure to generate locally:

- `assets/08_l2grid_vs_l2tree_chart.png`
- Content: replay throughput comparison for `l2tree` and `l2grid`

## Slide 10. Experimental Design and Main Results

Core message:

- All implementations were tested under the same configuration, so the comparison is fair.
- The results support the main claim that L2-specialized design improves research efficiency.

Suggested bullets:

- same dataset
- same replay limit
- same workload definitions
- same correctness rules

Suggested key conclusions:

- `L2TreeBook` clearly outperforms baseline in replay throughput and memory usage
- `L2VecBook` is query-efficient but unsuitable as the main replay structure
- the refreshed `L2GridBook` prototype shows that non-tree grid layouts are not automatically better; chunked sparse pages can hurt both replay and memory when locality assumptions are weak

Data figures to generate locally:

- `assets/09_replay_throughput.png`
- `assets/10_microbench.png`
- `assets/11_peak_rss.png`

Recommended note:

- This page should use real charts, not AI illustrations

## Slide 11. Current Value, Risks, and Next Steps

Core message:

- The project already improves local research efficiency.
- The remaining work is focused and feasible.

Suggested bullets:

- Current value:
  - faster local replay
  - lower memory overhead
  - clearer understanding of design trade-offs
- Risks:
  - `L2GridBook` page sparsity, memory amplification, and tuning
  - further integration complexity for live usage
- Next steps:
  - refine `L2GridBook`
  - polish experiment plots and thesis chapters
  - study how to connect the optimized L2 engine to a more realistic live path

Figure plan:

- Future roadmap diagram

Asset:

- `assets/12_future_work.png`

Prompt for Gemini:
`academic roadmap showing current research prototype evolving into stable L2 engine, integration with local persistence, research workflow, and future live trading deployment, clean vector style, white background, no text`

## Figures We Should Generate Ourselves

These figures should come from real experimental data rather than Gemini:

- `assets/06_l2tree_vs_baseline_highlight.png`
- `assets/07_l2vec_tradeoff_chart.png`
- `assets/08_l2grid_vs_l2tree_chart.png`
- `assets/09_replay_throughput.png`
- `assets/10_microbench.png`
- `assets/11_peak_rss.png`

Data sources:

- `results/baseline/phase0_subset_10m_r3_q100_q1000/`
- `results/phase1/l2tree_vs_baseline_subset_10m_r3_q100_q1000/`
- `results/comparisons/all_books_subset_10m_r3_q100_q1000/`

## Speaker Notes Style

Suggested tone:

- problem first
- evidence driven
- honest about trade-offs
- clear that current value is research acceleration, while the final target is live integration

Avoid:

- claiming the work is already production-ready
- overclaiming that all open-source L2 systems are absent
- presenting conceptual figures as experimental evidence
