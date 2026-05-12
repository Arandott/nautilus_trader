# Slide Assets Manifest

This directory stores both Gemini-generated concept images and locally generated
data figures for the midterm defense deck.

## Gemini Assets

- `00_cover_bg.png`
- `01_l2_research_motivation.png`
- `02_problem_scope.png`
- `03_baseline_path.png`
- `04_overhead_method.png`
- `05_technical_roadmap.png`
- `06_l2treebook_diagram.png`
- `07_l2vecbook_diagram.png`
- `08_l2gridbook_diagram.png`
- `12_future_work.png`

## Data Figures

The current Beamer source renders the following charts directly from
`src/data/*.csv` with `pgfplots`:

- replay throughput comparison
- microbenchmark comparison
- peak RSS comparison

If needed later, they can also be exported as standalone PDF figures.

The slide source supports missing Gemini assets by showing placeholders, so the
deck can be edited before the final images are ready.
