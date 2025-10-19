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
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow.feather as feather
from tqdm import tqdm

from nautilus_trader.core.nautilus_pyo3 import Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import BarDataWranglerV2
from nautilus_trader.test_kit.providers import TestInstrumentProvider


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
    parser.add_argument("--instrument-type", type=str, default="perp", choices=["spot", "perp", "future"], help="Instrument type: spot (no suffix), perp (-PERP), future (-FUTURE) (default: perp)")
    parser.add_argument("--bar-step", type=int, default=15, help="Bar step size in minutes (default: 15)")
    parser.add_argument("--aggregation", type=str, default="MINUTE", choices=["MINUTE"], help="Aggregation unit (currently only MINUTE)")
    parser.add_argument("--price-type", type=str, default="LAST", help="Price type segment (default: LAST)")
    parser.add_argument("--aggregation-source", type=str, default="EXTERNAL", help="Aggregation source segment (default: EXTERNAL)")
    parser.add_argument("--price-precision", type=int, default=None, help="Price precision (default: auto-detect from TestInstrumentProvider or data)")
    parser.add_argument("--size-precision", type=int, default=None, help="Size precision (default: auto-detect from TestInstrumentProvider or data)")
    parser.add_argument("--dry-run", action="store_true", help="Parse inputs and report stats without writing Parquet files")
    parser.add_argument("--quiet", action="store_true", help="Disable progress bars")
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

    # Forward-fill NaN values in all data columns (per symbol)
    # This handles trading halts or data gaps by propagating the last known value
    # Note: BarDataWranglerV2 expects clean data (nullable=False in PyArrow schema)
    data_cols = ["open", "high", "low", "close", "volume", "amt"]
    if df[data_cols].isna().any().any():
        # Group by symbol and forward-fill within each group
        df[data_cols] = df.groupby("code")[data_cols].ffill()

        # Drop rows that still have NaN (first bars of each symbol if they start with NaN)
        remaining_nan = df[data_cols].isna().any(axis=1)
        if remaining_nan.any():
            nan_count = remaining_nan.sum()
            symbols_affected = df.loc[remaining_nan, "code"].unique()
            print(
                f"  Warning: {file_path.stem} - dropping {nan_count} rows with leading NaN "
                f"(symbols: {', '.join(symbols_affected)})",
                file=sys.stderr,
            )
            df = df[~remaining_nan].copy()

    return df


def build_bar_type(symbol: str, venue: str, step: int, aggregation: str, price_type: str, source: str, instrument_type: str = "spot") -> str:
    """
    Build bar type string with optional instrument type suffix.

    Parameters
    ----------
    symbol : str
        Base symbol (e.g., "BTCUSDT")
    venue : str
        Venue name (e.g., "BINANCE")
    step : int
        Bar step size
    aggregation : str
        Aggregation unit (e.g., "MINUTE")
    price_type : str
        Price type (e.g., "LAST")
    source : str
        Aggregation source (e.g., "EXTERNAL")
    instrument_type : str
        Instrument type: "spot" (no suffix), "perp" (-PERP), "future" (-FUTURE)

    Returns
    -------
    str
        Bar type string (e.g., "BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-EXTERNAL")
    """
    # Add suffix based on instrument type
    if instrument_type == "perp":
        symbol_with_suffix = f"{symbol}-PERP"
    elif instrument_type == "future":
        symbol_with_suffix = f"{symbol}-FUTURE"
    else:  # spot
        symbol_with_suffix = symbol

    return f"{symbol_with_suffix}.{venue}-{step}-{aggregation}-{price_type}-{source}"


def get_decimal_precision(value: float) -> int:
    """Get decimal precision of a float value."""
    if pd.isna(value) or value == 0:
        return 0
    decimal_str = f"{value:.15f}".rstrip("0").rstrip(".")
    if "." not in decimal_str:
        return 0
    return len(decimal_str.split(".")[1])


def detect_data_precision(df: pd.DataFrame, column: str) -> int:
    """Detect maximum precision in a DataFrame column by scanning all values."""
    max_precision = 0
    # Sample up to 10000 rows to avoid performance issues
    sample_size = min(10000, len(df))
    sample = df[column].sample(n=sample_size, random_state=42) if len(df) > sample_size else df[column]

    for value in sample:
        if pd.notna(value):
            precision = get_decimal_precision(value)
            max_precision = max(max_precision, precision)

    return max_precision


def resolve_bars_precision(
    symbol: str,
    venue: str,
    price_precision: int | None = None,
    size_precision: int | None = None,
    df: pd.DataFrame | None = None,
) -> tuple[int, int]:
    """
    Resolve price and size precision for a symbol.

    Strategy:
    1. Use explicit CLI overrides if provided
    2. Try TestInstrumentProvider for known instruments
    3. Fall back to data scanning if neither is available

    Parameters
    ----------
    symbol : str
        Trading symbol (e.g., "BTCUSDT")
    venue : str
        Venue name (e.g., "BINANCE")
    price_precision : int | None
        Explicit price precision override
    size_precision : int | None
        Explicit size precision override
    df : pd.DataFrame | None
        Data frame to scan if auto-detection is needed

    Returns
    -------
    tuple[int, int]
        (price_precision, size_precision)

    Raises
    ------
    ValueError
        If precision cannot be resolved (no CLI override, no provider, no data)
    """
    resolved_price = price_precision
    resolved_size = size_precision
    source = "CLI override"

    # Try TestInstrumentProvider for known instruments
    if resolved_price is None or resolved_size is None:
        try:
            provider = TestInstrumentProvider()
            instrument_method = f"{symbol.lower()}_{venue.lower()}"
            if hasattr(provider, instrument_method):
                instrument = getattr(provider, instrument_method)()
                if resolved_price is None:
                    resolved_price = instrument.price_precision
                if resolved_size is None:
                    resolved_size = instrument.size_precision
                source = "TestInstrumentProvider"
        except Exception:
            pass  # Fall through to data scanning

    # Fall back to data scanning
    if (resolved_price is None or resolved_size is None) and df is not None:
        if resolved_price is None:
            # Scan OHLC columns for max precision
            price_cols = ["open", "high", "low", "close"]
            max_price_precision = 0
            for col in price_cols:
                if col in df.columns:
                    col_precision = detect_data_precision(df, col)
                    max_price_precision = max(max_price_precision, col_precision)
            resolved_price = max_price_precision

        if resolved_size is None and "volume" in df.columns:
            resolved_size = detect_data_precision(df, "volume")

        source = "data scanning"

    # Validate we have both values
    if resolved_price is None or resolved_size is None:
        raise ValueError(
            f"Cannot resolve precision for {symbol}.{venue}: "
            f"price_precision={resolved_price}, size_precision={resolved_size}. "
            f"Provide --price-precision and --size-precision or ensure data is available."
        )

    return resolved_price, resolved_size, source


def quantize_dataframe(
    df: pd.DataFrame,
    price_precision: int,
    size_precision: int,
) -> pd.DataFrame:
    """
    Quantize OHLCV data to target precision using Decimal for accuracy.

    Parameters
    ----------
    df : pd.DataFrame
        Data frame with OHLC, volume, and amt columns
    price_precision : int
        Target precision for price columns (open, high, low, close)
    size_precision : int
        Target precision for size column (volume)

    Returns
    -------
    pd.DataFrame
        Quantized data frame (copy)
    """
    df = df.copy()

    # Quantize price columns
    price_cols = ["open", "high", "low", "close"]
    quantizer = Decimal(10) ** -price_precision

    for col in price_cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: float(Decimal(str(x)).quantize(quantizer)) if pd.notna(x) else x
            )

    # Quantize volume
    if "volume" in df.columns:
        vol_quantizer = Decimal(10) ** -size_precision
        df["volume"] = df["volume"].apply(
            lambda x: float(Decimal(str(x)).quantize(vol_quantizer)) if pd.notna(x) else x
        )

    # Note: amt precision is less critical and will be handled by Quantity serialization

    return df


def build_quantity(value: float, precision: int) -> Quantity:
    scale = 10 ** precision
    raw = int(round(value * scale))
    return Quantity.from_raw(raw, precision)


def collect_rows(root: Path, symbols: Iterable[str], start: datetime | None, end: datetime | None, *, quiet: bool = False) -> dict[str, pd.DataFrame]:
    frames: dict[str, list[pd.DataFrame]] = defaultdict(list)

    # Convert to list to get count for progress bar
    file_list = list(iter_feather_files(root, start, end))

    for file_path in tqdm(file_list, desc="Collecting data", unit="file", disable=quiet):
        df = normalise_dataframe(file_path)
        for symbol in symbols:
            subset = df[df["code"].str.upper() == symbol.upper()]
            if not subset.empty:
                frames[symbol].append(subset)
    return {symbol: pd.concat(frames_list, ignore_index=True).sort_values("ts_event") for symbol, frames_list in frames.items() if frames_list}


def detect_symbols(root: Path, start: datetime | None, end: datetime | None, *, quiet: bool = False) -> list[str]:
    symbols: set[str] = set()

    # Convert to list to get count for progress bar
    file_list = list(iter_feather_files(root, start, end))

    for file_path in tqdm(file_list, desc="Scanning symbols", unit="file", disable=quiet):
        table = feather.read_table(file_path, columns=["code"])
        symbols.update(code.upper() for code in table.column("code").to_pylist())
    return sorted(symbols)


def build_catalog(
    catalog_path: Path,
    symbol_frames: dict[str, pd.DataFrame],
    venue: str,
    step: int,
    aggregation: str,
    price_type: str,
    source: str,
    instrument_type: str,
    price_precision: int | None,
    size_precision: int | None,
    dry_run: bool,
    *,
    quiet: bool = False,
) -> list[ConversionStats]:
    catalog_path = catalog_path.resolve()
    catalog_path.mkdir(parents=True, exist_ok=True)

    catalog = ParquetDataCatalog(str(catalog_path))
    stats: list[ConversionStats] = []

    # Progress bar for symbol conversion
    desc = "Converting (dry-run)" if dry_run else "Converting & writing"
    for symbol, df in tqdm(symbol_frames.items(), desc=desc, unit="symbol", disable=quiet):
        # Resolve precision for this symbol
        resolved_price_prec, resolved_size_prec, prec_source = resolve_bars_precision(
            symbol=symbol,
            venue=venue,
            price_precision=price_precision,
            size_precision=size_precision,
            df=df,
        )

        if not quiet:
            print(f"  {symbol}: price_precision={resolved_price_prec}, size_precision={resolved_size_prec} (source: {prec_source})")

        # Quantize data to target precision
        df_quantized = quantize_dataframe(df, resolved_price_prec, resolved_size_prec)

        bar_type = build_bar_type(symbol, venue, step, aggregation, price_type, source, instrument_type)
        wrangler = BarDataWranglerV2(bar_type=bar_type, price_precision=resolved_price_prec, size_precision=resolved_size_prec)
        # Include 'amt' column for extended bar fields (wrangler auto-detects from EXTENDED_BAR_FIELD_SPECS)
        frame = df_quantized[["open", "high", "low", "close", "volume", "ts_event", "ts_init", "amt"]].copy()
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
        symbols = detect_symbols(feather_root, start, end, quiet=args.quiet)
    else:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]

    if not symbols:
        print("No symbols selected; nothing to do.", file=sys.stderr)
        return 0

    symbol_frames = collect_rows(feather_root, symbols, start, end, quiet=args.quiet)
    missing = sorted(set(symbols) - set(symbol_frames.keys()))
    if missing:
        print(f"Warning: no rows found for symbols {missing}", file=sys.stderr)

    stats = build_catalog(
        args.catalog_path,
        symbol_frames,
        args.venue.upper(),
        args.bar_step,
        args.aggregation.upper(),
        args.price_type.upper(),
        args.aggregation_source.upper(),
        args.instrument_type.lower(),  # Pass instrument type
        args.price_precision,
        args.size_precision,
        args.dry_run,
        quiet=args.quiet,
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
