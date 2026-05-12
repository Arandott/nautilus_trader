#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tomllib
from datetime import UTC
from datetime import datetime
from pathlib import Path


DEFAULT_DATASET = Path(
    "/home/ubuntu/michael/binance-futures_incremental_book_L2_2024-12-10_BTCUSDT.csv.gz",
)
BENCH_NAME = "l2_book_baseline_criterion"
RUNNER_BIN = "tardis-l2-baseline"
SUPPORTED_BOOKS = ["baseline", "l2tree", "l2vec", "l2grid"]
RUNNER_MODES = ["replay_only", "replay_periodic_query"]
DEFAULT_QUERY_INTERVALS = [100, 1000]
MICRO_CASES = [
    "update_existing_level",
    "insert_new_level",
    "delete_existing_level",
    "best_bid_ask",
    "top_10_query",
]
BENCH_PREFIX = {
    "baseline": "l2_baseline",
    "l2tree": "l2tree",
    "l2vec": "l2vec",
    "l2grid": "l2grid",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_output_root() -> Path:
    return repo_root() / "cufe_undergraduate_playground" / "results" / "comparisons"


def cargo_cmd() -> list[str]:
    toolchain_file = repo_root() / "rust-toolchain.toml"
    if toolchain_file.exists():
        toolchain = tomllib.loads(toolchain_file.read_text(encoding="utf-8"))
        version = toolchain.get("toolchain", {}).get("version")
        if version:
            return ["cargo", f"+{version}"]
    return ["cargo"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run shared L2 book comparison workloads across multiple implementations.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--books", type=str, default="baseline,l2tree")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--modes",
        type=str,
        default=",".join(RUNNER_MODES),
        help="Comma-separated runner modes. Valid values: replay_only,replay_periodic_query",
    )
    parser.add_argument(
        "--query-intervals",
        type=str,
        default=",".join(str(interval) for interval in DEFAULT_QUERY_INTERVALS),
        help="Comma-separated query intervals for replay_periodic_query mode",
    )
    parser.add_argument(
        "--skip-criterion",
        action="store_true",
        help="Skip the criterion microbenchmark stage",
    )
    return parser.parse_args()


def parse_books(raw: str) -> list[str]:
    books = [book.strip() for book in raw.split(",") if book.strip()]
    if not books:
        raise ValueError("At least one book must be provided")

    invalid = [book for book in books if book not in SUPPORTED_BOOKS]
    if invalid:
        raise ValueError(f"Invalid books: {', '.join(invalid)}")

    deduped: list[str] = []
    for book in books:
        if book not in deduped:
            deduped.append(book)
    return deduped


def parse_modes(raw: str) -> list[str]:
    modes = [mode.strip() for mode in raw.split(",") if mode.strip()]
    if not modes:
        raise ValueError("At least one runner mode must be provided")

    invalid = [mode for mode in modes if mode not in RUNNER_MODES]
    if invalid:
        raise ValueError(f"Invalid runner modes: {', '.join(invalid)}")

    deduped: list[str] = []
    for mode in modes:
        if mode not in deduped:
            deduped.append(mode)
    return deduped


def parse_query_intervals(raw: str) -> list[int]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values:
        return []

    intervals: list[int] = []
    for value in values:
        interval = int(value)
        if interval <= 0:
            raise ValueError("Query intervals must be positive integers")
        if interval not in intervals:
            intervals.append(interval)
    return intervals


def ensure_dirs(output_root: Path) -> tuple[Path, Path, Path]:
    raw_dir = output_root / "raw"
    processed_dir = output_root / "processed"
    summaries_dir = output_root / "summaries"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, processed_dir, summaries_dir


def run_command(cmd: list[str], cwd: Path, log_path: Path) -> None:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text("$ " + " ".join(cmd) + "\n\n" + result.stdout, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def collect_criterion_estimates(
    root: Path,
    books: list[str],
) -> dict[str, dict[str, dict[str, float | None]]]:
    criterion_root = root / "target" / "criterion"
    results: dict[str, dict[str, dict[str, float | None]]] = {}

    for book in books:
        prefix = BENCH_PREFIX[book]
        cases: dict[str, dict[str, float | None]] = {}
        for case in MICRO_CASES:
            estimate_path = criterion_root / f"{prefix}_{case}" / "new" / "estimates.json"
            if not estimate_path.exists():
                cases[case] = {"mean_point_estimate": None, "median_point_estimate": None}
                continue

            data = json.loads(estimate_path.read_text(encoding="utf-8"))
            cases[case] = {
                "mean_point_estimate": data.get("mean", {}).get("point_estimate"),
                "median_point_estimate": data.get("median", {}).get("point_estimate"),
            }
        results[book] = cases

    return results


def run_criterion(
    root: Path,
    raw_dir: Path,
    processed_dir: Path,
    books: list[str],
) -> dict[str, dict[str, dict[str, float | None]]]:
    log_path = raw_dir / "criterion_l2_books.log"
    cmd = [
        *cargo_cmd(),
        "bench",
        "-p",
        "nautilus-model",
        "--bench",
        BENCH_NAME,
        "--",
        "--noplot",
    ]
    run_command(cmd, root, log_path)
    estimates = collect_criterion_estimates(root, books)
    (processed_dir / "criterion_estimates.json").write_text(
        json.dumps(estimates, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return estimates


def run_runner_modes(
    root: Path,
    raw_dir: Path,
    books: list[str],
    repeats: int,
    dataset: Path,
    depth: int,
    limit: int | None,
    modes: list[str],
    query_intervals: list[int],
) -> list[dict]:
    results: list[dict] = []

    for book in books:
        for mode in modes:
            runner_configs = (
                [(mode, interval) for interval in query_intervals]
                if mode == "replay_periodic_query"
                else [(mode, None)]
            )

            for runner_mode, query_interval in runner_configs:
                for repeat in range(1, repeats + 1):
                    suffix = f"{book}_{runner_mode}_r{repeat}"
                    if query_interval is not None:
                        suffix = f"{book}_{runner_mode}_q{query_interval}_r{repeat}"

                    output_json = raw_dir / f"{suffix}.json"
                    log_path = raw_dir / f"{suffix}.log"
                    cmd = [
                        *cargo_cmd(),
                        "run",
                        "-p",
                        "nautilus-tardis",
                        "--bin",
                        RUNNER_BIN,
                        "--",
                        "--dataset",
                        str(dataset),
                        "--book",
                        book,
                        "--mode",
                        runner_mode,
                        "--depth",
                        str(depth),
                        "--output",
                        str(output_json),
                    ]
                    if query_interval is not None:
                        cmd.extend(["--query-interval", str(query_interval)])
                    if limit is not None:
                        cmd.extend(["--limit", str(limit)])

                    run_command(cmd, root, log_path)
                    results.append(json.loads(output_json.read_text(encoding="utf-8")))

    return results


def summarize_runner_results(records: list[dict]) -> dict[str, dict[str, float | int | str | None]]:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        key = f"{record['book']}::{record['mode']}"
        if record.get("query_interval") is not None:
            key = f"{key}::q{record['query_interval']}"
        grouped.setdefault(key, []).append(record)

    summary: dict[str, dict[str, float | int | str | None]] = {}
    for key, items in grouped.items():
        summary[key] = {
            "book": items[0]["book"],
            "mode": items[0]["mode"],
            "query_interval": items[0]["query_interval"],
            "runs": len(items),
            "avg_elapsed_ns": int(statistics.mean(item["elapsed_ns"] for item in items)),
            "avg_updates_per_sec": statistics.mean(item["updates_per_sec"] for item in items),
            "avg_query_ns": int(statistics.mean(item["avg_query_ns"] for item in items)),
            "max_query_ns": max(item["max_query_ns"] for item in items),
            "avg_peak_resident_bytes": int(
                statistics.mean(item["peak_resident_bytes"] or 0 for item in items),
            ),
            "total_deltas": items[0]["total_deltas"],
        }

    return summary


def write_summary_markdown(
    path: Path,
    dataset: Path,
    books: list[str],
    criterion_estimates: dict[str, dict[str, dict[str, float | None]]],
    runner_summary: dict[str, dict[str, float | int | str | None]],
) -> None:
    lines = [
        "# L2 Book Comparison Summary",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Dataset: `{dataset}`",
        f"- Books: `{', '.join(books)}`",
    ]

    if criterion_estimates:
        lines.extend(
            [
                "",
                "## Criterion",
                "",
                "| Book | Case | Mean point estimate | Median point estimate |",
                "| --- | --- | ---: | ---: |",
            ],
        )
        for book in books:
            for case in MICRO_CASES:
                estimate = criterion_estimates.get(book, {}).get(case, {})
                lines.append(
                    f"| `{book}` | `{case}` | {estimate.get('mean_point_estimate')} | "
                    f"{estimate.get('median_point_estimate')} |",
                )

    if runner_summary:
        lines.extend(
            [
                "",
                "## Replay Runner",
                "",
                "| Key | Runs | Avg elapsed (ns) | Avg updates/s | Avg query (ns) | "
                "Max query (ns) | Avg peak RSS (bytes) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ],
        )

        for key in sorted(runner_summary):
            item = runner_summary[key]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{key}`",
                        str(item["runs"]),
                        str(item["avg_elapsed_ns"]),
                        f"{item['avg_updates_per_sec']:.2f}",
                        str(item["avg_query_ns"]),
                        str(item["max_query_ns"]),
                        str(item["avg_peak_resident_bytes"]),
                    ],
                )
                + " |",
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = repo_root()
    raw_dir, processed_dir, summaries_dir = ensure_dirs(args.output_root)
    books = parse_books(args.books)
    modes = parse_modes(args.modes)
    query_intervals = parse_query_intervals(args.query_intervals)
    if "replay_periodic_query" in modes and not query_intervals:
        raise ValueError(
            "`--query-intervals` must contain at least one value when replay_periodic_query is enabled",
        )

    criterion_estimates: dict[str, dict[str, dict[str, float | None]]] = {}
    if not args.skip_criterion:
        criterion_estimates = run_criterion(root, raw_dir, processed_dir, books)

    runner_records = run_runner_modes(
        root=root,
        raw_dir=raw_dir,
        books=books,
        repeats=args.repeats,
        dataset=args.dataset,
        depth=args.depth,
        limit=args.limit,
        modes=modes,
        query_intervals=query_intervals,
    )
    runner_summary = summarize_runner_results(runner_records)

    (processed_dir / "runner_records.json").write_text(
        json.dumps(runner_records, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (processed_dir / "runner_summary.json").write_text(
        json.dumps(runner_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_summary_markdown(
        summaries_dir / "comparison_summary.md",
        args.dataset,
        books,
        criterion_estimates,
        runner_summary,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
