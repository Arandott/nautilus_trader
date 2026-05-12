from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = (
    ROOT
    / "cufe_undergraduate_playground"
    / "results"
    / "comparisons"
    / "all_books_subset_10m_r3_q100_q1000_final_2026-04-10"
    / "processed"
)
OUT_DIR = Path(__file__).resolve().parent / "figures"

BOOKS = ["baseline", "l2tree", "l2vec", "l2grid"]
BOOK_LABELS = {
    "baseline": "baseline",
    "l2tree": "L2TreeBook",
    "l2vec": "L2VecBook",
    "l2grid": "L2GridBook",
}
COLORS = {
    "baseline": "#7F8C8D",
    "l2tree": "#1B9E77",
    "l2vec": "#D95F02",
    "l2grid": "#7570B3",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def grouped_bar_chart(
    *,
    categories: list[str],
    series: dict[str, list[float]],
    ylabel: str,
    title: str,
    output: Path,
    value_fmt: str,
) -> None:
    plt.style.use("default")
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(categories))
    width = 0.18

    for i, book in enumerate(BOOKS):
        values = series[book]
        offset = (i - 1.5) * width
        bars = ax.bar(
            x + offset,
            values,
            width=width,
            label=BOOK_LABELS[book],
            color=COLORS[book],
            edgecolor="black",
            linewidth=0.6,
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                value_fmt.format(value),
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=0,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=12)
    ax.legend(frameon=False, ncol=2)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output, format="svg")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runner_summary = load_json(RESULT_DIR / "runner_summary.json")
    criterion = load_json(RESULT_DIR / "criterion_estimates.json")

    replay_categories = ["replay_only", "periodic_q100", "periodic_q1000"]
    replay_series = {
        "baseline": [
            runner_summary["baseline::replay_only"]["avg_updates_per_sec"] / 1000,
            runner_summary["baseline::replay_periodic_query::q100"]["avg_updates_per_sec"] / 1000,
            runner_summary["baseline::replay_periodic_query::q1000"]["avg_updates_per_sec"] / 1000,
        ],
        "l2tree": [
            runner_summary["l2tree::replay_only"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2tree::replay_periodic_query::q100"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2tree::replay_periodic_query::q1000"]["avg_updates_per_sec"] / 1000,
        ],
        "l2vec": [
            runner_summary["l2vec::replay_only"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2vec::replay_periodic_query::q100"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2vec::replay_periodic_query::q1000"]["avg_updates_per_sec"] / 1000,
        ],
        "l2grid": [
            runner_summary["l2grid::replay_only"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2grid::replay_periodic_query::q100"]["avg_updates_per_sec"] / 1000,
            runner_summary["l2grid::replay_periodic_query::q1000"]["avg_updates_per_sec"] / 1000,
        ],
    }
    grouped_bar_chart(
        categories=replay_categories,
        series=replay_series,
        ylabel="Throughput (k updates/s)",
        title="Replay throughput under three workloads",
        output=OUT_DIR / "replay_throughput.svg",
        value_fmt="{:.1f}",
    )

    query_categories = ["q100", "q1000"]
    query_series = {
        "baseline": [
            runner_summary["baseline::replay_periodic_query::q100"]["avg_query_ns"],
            runner_summary["baseline::replay_periodic_query::q1000"]["avg_query_ns"],
        ],
        "l2tree": [
            runner_summary["l2tree::replay_periodic_query::q100"]["avg_query_ns"],
            runner_summary["l2tree::replay_periodic_query::q1000"]["avg_query_ns"],
        ],
        "l2vec": [
            runner_summary["l2vec::replay_periodic_query::q100"]["avg_query_ns"],
            runner_summary["l2vec::replay_periodic_query::q1000"]["avg_query_ns"],
        ],
        "l2grid": [
            runner_summary["l2grid::replay_periodic_query::q100"]["avg_query_ns"],
            runner_summary["l2grid::replay_periodic_query::q1000"]["avg_query_ns"],
        ],
    }
    grouped_bar_chart(
        categories=query_categories,
        series=query_series,
        ylabel="Average query latency (ns)",
        title="Periodic-query latency comparison",
        output=OUT_DIR / "query_latency.svg",
        value_fmt="{:.0f}",
    )

    rss_categories = ["replay_only", "periodic_q100", "periodic_q1000"]
    rss_series = {
        "baseline": [
            runner_summary["baseline::replay_only"]["avg_peak_resident_bytes"] / (1024 * 1024),
            runner_summary["baseline::replay_periodic_query::q100"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
            runner_summary["baseline::replay_periodic_query::q1000"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
        ],
        "l2tree": [
            runner_summary["l2tree::replay_only"]["avg_peak_resident_bytes"] / (1024 * 1024),
            runner_summary["l2tree::replay_periodic_query::q100"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
            runner_summary["l2tree::replay_periodic_query::q1000"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
        ],
        "l2vec": [
            runner_summary["l2vec::replay_only"]["avg_peak_resident_bytes"] / (1024 * 1024),
            runner_summary["l2vec::replay_periodic_query::q100"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
            runner_summary["l2vec::replay_periodic_query::q1000"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
        ],
        "l2grid": [
            runner_summary["l2grid::replay_only"]["avg_peak_resident_bytes"] / (1024 * 1024),
            runner_summary["l2grid::replay_periodic_query::q100"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
            runner_summary["l2grid::replay_periodic_query::q1000"]["avg_peak_resident_bytes"]
            / (1024 * 1024),
        ],
    }
    grouped_bar_chart(
        categories=rss_categories,
        series=rss_series,
        ylabel="Peak RSS (MiB)",
        title="Peak memory comparison",
        output=OUT_DIR / "peak_rss.svg",
        value_fmt="{:.1f}",
    )

    criterion_categories = [
        "update_existing",
        "insert_new",
        "delete_existing",
        "best_bid_ask",
        "top_10_query",
    ]
    criterion_series = {
        "baseline": [
            criterion["baseline"]["update_existing_level"]["mean_point_estimate"],
            criterion["baseline"]["insert_new_level"]["mean_point_estimate"],
            criterion["baseline"]["delete_existing_level"]["mean_point_estimate"],
            criterion["baseline"]["best_bid_ask"]["mean_point_estimate"],
            criterion["baseline"]["top_10_query"]["mean_point_estimate"],
        ],
        "l2tree": [
            criterion["l2tree"]["update_existing_level"]["mean_point_estimate"],
            criterion["l2tree"]["insert_new_level"]["mean_point_estimate"],
            criterion["l2tree"]["delete_existing_level"]["mean_point_estimate"],
            criterion["l2tree"]["best_bid_ask"]["mean_point_estimate"],
            criterion["l2tree"]["top_10_query"]["mean_point_estimate"],
        ],
        "l2vec": [
            criterion["l2vec"]["update_existing_level"]["mean_point_estimate"],
            criterion["l2vec"]["insert_new_level"]["mean_point_estimate"],
            criterion["l2vec"]["delete_existing_level"]["mean_point_estimate"],
            criterion["l2vec"]["best_bid_ask"]["mean_point_estimate"],
            criterion["l2vec"]["top_10_query"]["mean_point_estimate"],
        ],
        "l2grid": [
            criterion["l2grid"]["update_existing_level"]["mean_point_estimate"],
            criterion["l2grid"]["insert_new_level"]["mean_point_estimate"],
            criterion["l2grid"]["delete_existing_level"]["mean_point_estimate"],
            criterion["l2grid"]["best_bid_ask"]["mean_point_estimate"],
            criterion["l2grid"]["top_10_query"]["mean_point_estimate"],
        ],
    }
    grouped_bar_chart(
        categories=criterion_categories,
        series=criterion_series,
        ylabel="Mean estimate (ns)",
        title="Criterion microbenchmark comparison",
        output=OUT_DIR / "criterion_cases.svg",
        value_fmt="{:.1f}",
    )


if __name__ == "__main__":
    main()
