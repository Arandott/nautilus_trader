"""
Data access utilities for research workflows.

Provides helpers for:
- Loading bar data from Parquet catalog
- Resolving instrument IDs and calendars
- Managing data source configuration
"""

from pathlib import Path

import pandas as pd

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog


def get_catalog_path() -> Path:
    """
    Return the default catalog path for research data.

    Returns
    -------
    Path
        Path to factorexp_backtest/catalog directory.
    """
    # Navigate from this file: research/utils/ -> research/ -> factorexp_backtest/
    research_path = Path(__file__).parent.parent
    factorexp_backtest_path = research_path.parent
    catalog_path = factorexp_backtest_path / "catalog"

    if not catalog_path.exists():
        raise FileNotFoundError(
            f"Catalog directory not found at {catalog_path}. "
            "Please ensure data has been prepared."
        )

    return catalog_path


def load_catalog_bars(
    instrument_id: str,
    start_date: str,
    end_date: str,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """
    Load bar data from Parquet catalog.

    Parameters
    ----------
    instrument_id : str
        Instrument identifier (e.g., "BTCUSDT.BINANCE")
    start_date : str
        Start date in 'YYYY-MM-DD' format
    end_date : str
        End date in 'YYYY-MM-DD' format
    catalog_path : Path, optional
        Custom catalog path. If None, uses default catalog location.

    Returns
    -------
    pd.DataFrame
        Bar data with columns: open, high, low, close, volume, ts_event, ts_init, etc.

    Examples
    --------
    >>> bars = load_catalog_bars(
    ...     "BTCUSDT.BINANCE",
    ...     "2024-01-01",
    ...     "2024-01-31"
    ... )
    >>> print(bars.head())
    """
    if catalog_path is None:
        catalog_path = get_catalog_path()

    catalog = ParquetDataCatalog(str(catalog_path))

    # Convert string to InstrumentId
    instrument_id_obj = InstrumentId.from_str(instrument_id)

    # Load bars (returns list of Bar objects)
    bars_list = catalog.bars(
        instrument_ids=[instrument_id_obj],
        start=pd.Timestamp(start_date),
        end=pd.Timestamp(end_date),
    )

    if not bars_list:
        raise ValueError(
            f"No data found for {instrument_id} between {start_date} and {end_date}. "
            "Check instrument ID and date range."
        )

    # Convert Bar objects to DataFrame
    data = []
    for bar in bars_list:
        row = {
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
            "ts_event": int(bar.ts_event),
            "ts_init": int(bar.ts_init),
            "bar_type": bar.bar_type,
        }

        # Add extended fields if available
        if hasattr(bar, "amt"):
            row["amt"] = float(bar.amt)
        if hasattr(bar, "vwap_return"):
            row["vwap_return"] = float(bar.vwap_return)

        data.append(row)

    bars_df = pd.DataFrame(data)

    return bars_df


def get_available_instruments(catalog_path: Path | None = None) -> list[str]:
    """
    List all available instruments in the catalog.

    This function scans the bar data directory to find all available instruments,
    since the catalog may not have instrument definitions registered.

    Parameters
    ----------
    catalog_path : Path, optional
        Custom catalog path. If None, uses default catalog location.

    Returns
    -------
    List[str]
        List of instrument ID strings available in catalog (e.g., "BTCUSDT.BINANCE").

    Examples
    --------
    >>> instruments = get_available_instruments()
    >>> print(f"Found {len(instruments)} instruments")
    >>> print(instruments[:5])  # First 5 instruments
    ['BTCUSDT.BINANCE', 'ETHUSDT.BINANCE', ...]
    """
    if catalog_path is None:
        catalog_path = get_catalog_path()

    # Check bar data directory
    bar_path = catalog_path / "data" / "bar"
    if not bar_path.exists():
        return []

    # Extract instrument IDs from directory names
    # Directory format: "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
    # We want: "BTCUSDT.BINANCE"
    instrument_ids = []

    for dir_path in bar_path.iterdir():
        if not dir_path.is_dir():
            continue

        dir_name = dir_path.name
        # Split by first dash to separate instrument ID from bar spec
        # Example: "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL" -> "BTCUSDT.BINANCE"
        if "-" in dir_name:
            instrument_id = dir_name.split("-")[0]
            instrument_ids.append(instrument_id)

    return sorted(set(instrument_ids))  # Remove duplicates and sort
