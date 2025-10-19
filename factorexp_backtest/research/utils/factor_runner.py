"""
Factor expression evaluation engine for research workflows.

Provides simplified interface for evaluating factor expressions on bar data
outside the full backtest engine context.
"""

import sys
from pathlib import Path

import pandas as pd

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.identifiers import InstrumentId


def evaluate_factor(
    expression: str,
    instrument_id: str,
    start_date: str,
    end_date: str,
    catalog_path: Path | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Evaluate factor expression on bar data and return results.

    Loads bar data from catalog, creates a FactorExpIndicator, processes all bars,
    and returns computed factor values as a DataFrame. Progress and statistics are
    printed to stdout if verbose=True.

    Parameters
    ----------
    expression : str
        Factor expression string (e.g., "ZScore(TS_Std($close, 20), 5760)")
    instrument_id : str
        Instrument identifier (e.g., "BTCUSDT.BINANCE")
    start_date : str
        Start date in 'YYYY-MM-DD' format
    end_date : str
        End date in 'YYYY-MM-DD' format
    catalog_path : Path, optional
        Custom catalog path. If None, uses default catalog location.
    verbose : bool, default=True
        Enable progress output and statistics

    Returns
    -------
    pd.DataFrame
        Factor values with columns:
        - ts_event: Event timestamp (datetime)
        - ts_init: Initialization timestamp (datetime)
        - factor_value: Computed factor value
        - bar_close: Bar close price
        - bar_volume: Bar volume

    Examples
    --------
    >>> from factorexp_backtest.research.utils import evaluate_factor
    >>>
    >>> result = evaluate_factor(
    ...     "ZScore(TS_Std($close, 20), 5760)",
    ...     "BTCUSDT.BINANCE",
    ...     "2024-01-01",
    ...     "2024-01-31"
    ... )
    >>> print(result.head())
    >>> print(f"Valid values: {result['factor_value'].notna().sum()}")
    """
    from nautilus_trader.persistence.catalog import ParquetDataCatalog

    from .data_access import get_catalog_path

    # Resolve catalog path
    if catalog_path is None:
        catalog_path = get_catalog_path()

    # Load bars from catalog
    if verbose:
        print("Loading bar data...", flush=True)
        print(f"Catalog path: {catalog_path}", flush=True)

    catalog = ParquetDataCatalog(str(catalog_path))
    instrument_id_obj = InstrumentId.from_str(instrument_id)

    if verbose:
        print(f"Loading bars for {instrument_id} from {start_date} to {end_date}", flush=True)

    bars = catalog.bars(
        instrument_ids=[instrument_id_obj],
        start=pd.Timestamp(start_date),
        end=pd.Timestamp(end_date),
    )

    if not bars:
        raise ValueError(
            f"No data found for {instrument_id} between {start_date} and {end_date}"
        )

    if verbose:
        print(f"Loaded {len(bars)} bars", flush=True)

    # Create indicator
    if verbose:
        print(f"Initializing FactorExpIndicator with expression: {expression}", flush=True)

    indicator = FactorExpIndicator(expression=expression)

    # Process bars and collect results
    results = []

    if verbose:
        from tqdm import tqdm
        bar_iterator = tqdm(
            bars,
            desc="Processing bars",
            unit="bar",
            file=sys.stdout,
            dynamic_ncols=True,
            mininterval=0,
            maxinterval=0,
            miniters=1,
        )
    else:
        bar_iterator = bars

    for bar in bar_iterator:
        indicator.handle_bar(bar)

        # Collect result if indicator is initialized
        if indicator.initialized:
            results.append(
                {
                    "ts_event": int(bar.ts_event),
                    "ts_init": int(bar.ts_init),
                    "factor_value": indicator.value,
                    "bar_close": float(bar.close),
                    "bar_volume": float(bar.volume),
                }
            )

    # Convert to DataFrame
    result_df = pd.DataFrame(results)

    # Convert nanosecond timestamps to datetime for readability
    if not result_df.empty:
        result_df["ts_event"] = pd.to_datetime(result_df["ts_event"], unit="ns")
        result_df["ts_init"] = pd.to_datetime(result_df["ts_init"], unit="ns")

    return result_df
