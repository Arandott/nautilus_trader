# Midterm Slides

This directory contains the LaTeX source and supporting materials for the
undergraduate thesis midterm presentation.

## Layout

- `src/`: Beamer source files, bibliography, and local style files
- `assets/`: figures, logos, and exported plots used in the deck
- `build/`: generated PDFs and temporary LaTeX build artifacts
- `notes/`: speaking notes, outline drafts, and slide TODOs

## Notes

Keep generated files under `build/` so the source tree stays clean.
Reuse plots from `../figures/` when they are final enough for presentation.
The current slide source uses `ctexbeamer`, and chart data is stored under
`src/data/`.

## Build

Recommended command after a TeX environment is installed:

```bash
cd cufe_undergraduate_playground/slides/midterm/src
latexmk -xelatex -outdir=../build main.tex
```

If `latexmk` is unavailable, `xelatex` can also be used directly.
