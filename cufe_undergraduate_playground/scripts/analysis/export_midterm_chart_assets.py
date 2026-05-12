#!/usr/bin/env python3

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SLIDES_ROOT = REPO_ROOT / "cufe_undergraduate_playground/slides/midterm"
CHART_SRC_DIR = SLIDES_ROOT / "src/charts"
BUILD_DIR = SLIDES_ROOT / "build/charts"
ASSETS_DIR = SLIDES_ROOT / "assets"
CHARTS = [
    "09_replay_throughput",
    "10_microbench",
    "11_peak_rss",
]


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for chart in CHARTS:
        tex = f"{chart}.tex"
        run(
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-outdir={BUILD_DIR}",
                tex,
            ],
            CHART_SRC_DIR,
        )

        pdf = BUILD_DIR / f"{chart}.pdf"
        png_prefix = ASSETS_DIR / chart
        run(["pdftoppm", "-png", "-singlefile", str(pdf), str(png_prefix)], REPO_ROOT)


if __name__ == "__main__":
    main()
