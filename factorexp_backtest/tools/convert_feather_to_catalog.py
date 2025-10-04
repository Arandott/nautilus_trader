#!/usr/bin/env python3
"""
Feather ➜ Parquet catalog converter for FactorExp backtests.

This utility reads per-day Feather/IPC files (``*.fea``) exported under
``factorexp_backtest/data`` and materialises Nautilus-compatible Parquet files via
``ParquetDataCatalog``. It supports multiple symbols and ensures the `amt`
extended field is attached to each bar using the newly wired serialization path.

Example usage (build catalog for BTCUSDT only)::

    python -m factorexp_backtest.tools.convert_feather_to_catalog \
        --feather-root factorexp_backtest/data/Binance_k_15min \
        --catalog-path factorexp_backtest/catalog \
        --symbols BTCUSDT \
        --bar-step 15 \
        --venue BINANCE

To convert every symbol in the Feather folder, omit ``--symbols`` or pass ``ALL``.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.feather as feather

from nautilus_trader.core.nautilus_pyo3 import Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2


@dataclass
class ConversionStats:
    symbol: str
    bar_type: str
    rows: int
    first_ts: int
    last_ts: int


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Feather bars into a Parquet catalog")
    parser.add_argument("--feather-root", type=Path, required=True, help="Directory containing daily .fea files")
    parser.add_argument("--catalog-path", type=Path, required=True, help="Destination catalog root (will be created)")
    parser.add_argument("--symbols", type=str, default="ALL", help="Comma-separated symbol list (default: ALL symbols in Feather files)")
    parser.add_argument("--start-date", type=str, default=None, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="Inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--venue", type=str, default="BINANCE", help="Venue component in bar type (default: BINANCE)")
    parser.add_argument("--bar-step", type=int, default=15, help="Bar step size in minutes (default: 15)")
    parser.add_argument("--aggregation", type=str, default="MINUTE", choices=["MINUTE"], help="Aggregation unit (currently only MINUTE)")
    parser.add_argument("--price-type", type=str, default="LAST", help="Price type segment (default: LAST)")
    parser.add_argument("--aggregation-source", type=str, default="EXTERNAL", help="Aggregation source segment (default: EXTERNAL)")
    parser.add_argument("--price-precision", type=int, default=6, help="Price precision passed to BarDataWranglerV2")
    parser.add_argument("--size-precision", type=int, default=0, help="Size precision passed to BarDataWranglerV2")
    parser.add_argument("--amt-precision", type=int, default=2, help="Fixed precision used for amt Quantity serialization")
    parser.add_argument("--dry-run", action="store_true", help="Parse inputs and report stats without writing Parquet files")
    return parser.parse_args(argv)


def iter_feather_files(root: Path, start: datetime | None, end: datetime | None) -> Iterator[Path]:
    for path in sorted(root.glob("*.fe[aa]")):
        try:
            day = datetime.strptime(path.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if start and day < start:
            continue
        if end and day > end:
            continue
        yield path


def normalise_dataframe(file_path: Path) -> pd.DataFrame:
    table = feather.read_table(file_path)
    df = table.to_pandas()
    df.columns = [col.lower() for col in df.columns]
    if "code" not in df.columns or "second" not in df.columns:
        raise ValueError(f"Unexpected schema in {file_path}: missing 'code'/'second'")
    file_date = datetime.strptime(file_path.stem, "%Y-%m-%d")
    seconds = pd.to_timedelta(df["second"])
    ts_event = (pd.Timestamp(file_date, tz="UTC") + seconds).astype("int64")
    df = df.rename(
        columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amt": "amt",
        }
    )
    df["ts_event"] = ts_event
    df["ts_init"] = ts_event
    return df


def build_bar_type(symbol: str, venue: str, step: int, aggregation: str, price_type: str, source: str) -> str:
    return f"{symbol}.{venue}-{step}-{aggregation}-{price_type}-{source}"


def build_quantity(value: float, precision: int) -> Quantity:
    scale = 10 ** precision
    raw = int(round(value * scale))
    return Quantity.from_raw(raw, precision)


def collect_rows(root: Path, symbols: Iterable[str], start: datetime | None, end: datetime | None) -> dict[str, pd.DataFrame]:
    frames: dict[str, list[pd.DataFrame]] = defaultdict(list)
    for file_path in iter_feather_files(root, start, end):
        df = normalise_dataframe(file_path)
        for symbol in symbols:
            subset = df[df["code"].str.upper() == symbol.upper()]
            if not subset.empty:
                frames[symbol].append(subset)
    return {symbol: pd.concat(frames_list, ignore_index=True).sort_values("ts_event") for symbol, frames_list in frames.items() if frames_list}


def detect_symbols(root: Path, start: datetime | None, end: datetime | None) -> list[str]:
    symbols: set[str] = set()
    for file_path in iter_feather_files(root, start, end):
        table = feather.read_table(file_path, columns=["code"])
        symbols.update(code.upper() for code in table.column("code").to_pylist())
    return sorted(symbols)


def build_catalog(
    root: Path,
    catalog_path: Path,
    symbol_frames: dict[str, pd.DataFrame],
    venue: str,
    step: int,
    aggregation: str,
    price_type: str,
    source: str,
    price_precision: int,
    size_precision: int,
    amt_precision: int,
    dry_run: bool,
) -> list[ConversionStats]:
    catalog_path = catalog_path.resolve()
    catalog_path.mkdir(parents=True, exist_ok=True)

    catalog = ParquetDataCatalog(str(catalog_path))
    stats: list[ConversionStats] = []

    for symbol, df in symbol_frames.items():
        bar_type = build_bar_type(symbol, venue, step, aggregation, price_type, source)
        wrangler = BarDataWranglerV2(bar_type=bar_type, price_precision=price_precision, size_precision=size_precision)
        # Include 'amt' column for extended bar fields (wrangler auto-detects from EXTENDED_BAR_FIELD_SPECS)
        frame = df[["open", "high", "low", "close", "volume", "ts_event", "ts_init", "amt"]].copy()
        bars = wrangler.from_pandas(frame)

        if dry_run:
            # Only capture stats without writing to disk.
            stats.append(
                ConversionStats(
                    symbol=symbol,
                    bar_type=bar_type,
                    rows=len(bars),
                    first_ts=int(frame["ts_event"].min()) if not frame.empty else 0,
                    last_ts=int(frame["ts_event"].max()) if not frame.empty else 0,
                )
            )
        else:
            if bars:
                catalog.write_data(bars)
                stats.append(
                    ConversionStats(
                        symbol=symbol,
                        bar_type=bar_type,
                        rows=len(bars),
                        first_ts=int(frame["ts_event"].min()),
                        last_ts=int(frame["ts_event"].max()),
                    )
                )
    return stats


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    feather_root = args.feather_root.resolve()
    if not feather_root.exists():
        raise FileNotFoundError(f"Feather root not found: {feather_root}")

    start = datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else None
    end = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else None

    if args.symbols.strip().upper() == "ALL":
        symbols = detect_symbols(feather_root, start, end)
    else:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]

    if not symbols:
        print("No symbols selected; nothing to do.", file=sys.stderr)
        return 0

    symbol_frames = collect_rows(feather_root, symbols, start, end)
    missing = sorted(set(symbols) - set(symbol_frames.keys()))
    if missing:
        print(f"Warning: no rows found for symbols {missing}", file=sys.stderr)

    stats = build_catalog(
        feather_root,
        args.catalog_path,
        symbol_frames,
        args.venue.upper(),
        args.bar_step,
        args.aggregation.upper(),
        args.price_type.upper(),
        args.aggregation_source.upper(),
        args.price_precision,
        args.size_precision,
        args.amt_precision,
        args.dry_run,
    )

    if not stats:
        print("No bars converted.")
        return 0

    print("\nConversion summary:")
    for entry in stats:
        start_iso = datetime.fromtimestamp(entry.first_ts / 1e9, tz=UTC).isoformat() if entry.first_ts else "-"
        end_iso = datetime.fromtimestamp(entry.last_ts / 1e9, tz=UTC).isoformat() if entry.last_ts else "-"
        print(f"  {entry.symbol:>12} | {entry.rows:6d} bars | {entry.bar_type} | {start_iso} -> {end_iso}")
    if args.dry_run:
        print("Dry-run mode: no data written to catalog.")
    else:
        print(f"Catalog written to {args.catalog_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
