#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_SUMMARY = (
    ROOT / "results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/runner_summary.json"
)
CRITERION_SUMMARY = (
    ROOT / "results/comparisons/all_books_subset_10m_r3_q100_q1000/processed/criterion_summary.json"
)
OUTPUT_DIR = ROOT / "slides/midterm/src/data"

BOOKS = ["baseline", "l2tree", "l2vec", "l2grid"]
RUNNER_ROWS = [
    ("replay", "replay_only", None),
    ("q100", "replay_periodic_query", 100),
    ("q1000", "replay_periodic_query", 1000),
]
MICROBENCH_ROWS = [
    ("update", "update_existing_level"),
    ("insert", "insert_new_level"),
    ("delete", "delete_existing_level"),
    ("best", "best_bid_ask"),
    ("top10", "top_10_query"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def runner_key(book: str, mode: str, query_interval: int | None) -> str:
    if query_interval is None:
        return f"{book}::{mode}"
    return f"{book}::{mode}::q{query_interval}"


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    runner = load_json(RUNNER_SUMMARY)
    criterion = load_json(CRITERION_SUMMARY)

    throughput_rows: list[list[object]] = []
    elapsed_rows: list[list[object]] = []
    rss_rows: list[list[object]] = []

    for label, mode, interval in RUNNER_ROWS:
        throughput = [label]
        elapsed = [label]
        rss = [label]
        for book in BOOKS:
            record = runner[runner_key(book, mode, interval)]
            throughput.append(f"{record['avg_updates_per_sec']:.2f}")
            elapsed.append(f"{record['avg_elapsed_ns'] / 1_000_000_000:.2f}")
            rss.append(f"{record['avg_peak_resident_bytes'] / (1024 * 1024):.2f}")
        throughput_rows.append(throughput)
        elapsed_rows.append(elapsed)
        rss_rows.append(rss)

    microbench_rows: list[list[object]] = []
    for label, case in MICROBENCH_ROWS:
        row = [label]
        for book in BOOKS:
            row.append(f"{criterion[book][case]['mean_point_estimate']:.3f}")
        microbench_rows.append(row)

    header = ["label", *BOOKS]
    write_csv(OUTPUT_DIR / "replay_throughput.csv", header, throughput_rows)
    write_csv(OUTPUT_DIR / "replay_elapsed_seconds.csv", header, elapsed_rows)
    write_csv(OUTPUT_DIR / "peak_rss_mb.csv", header, rss_rows)
    write_csv(OUTPUT_DIR / "microbench_ns.csv", header, microbench_rows)


if __name__ == "__main__":
    main()
