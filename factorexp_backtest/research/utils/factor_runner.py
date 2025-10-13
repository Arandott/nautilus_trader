"""Factor expression evaluation engine for research workflows.

Provides simplified interface for evaluating factor expressions on bar data
outside the full backtest engine context.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
import sys


@dataclass
class FactorRequest:
    """Request specification for factor evaluation.

    Attributes
    ----------
    expression : str
        Factor expression string (e.g., "Clip(ZScore(TS_Std(...), 5760), -2, 2)")
    instrument_id : str
        Instrument identifier (e.g., "BTCUSDT.BINANCE")
    start_date : str
        Start date in 'YYYY-MM-DD' format
    end_date : str
        End date in 'YYYY-MM-DD' format
    period : int, optional
        Period for ZScore calculation (default: 5760 for 60 days @ 15min bars)
    """

    expression: str
    instrument_id: str
    start_date: str
    end_date: str
    period: int = 5760


def run_expression(
    request: FactorRequest,
    bars_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Evaluate factor expression on bar data.

    This function creates a FactorExpIndicator, feeds it bar data,
    and returns the computed factor values as a DataFrame.

    Parameters
    ----------
    request : FactorRequest
        Factor evaluation request specification
    bars_df : pd.DataFrame, optional
        Pre-loaded bar data. If None, will load from catalog.

    Returns
    -------
    pd.DataFrame
        Factor values with columns:
        - ts_event: Event timestamp
        - ts_init: Initialization timestamp
        - factor_value: Computed factor value
        - bar_close: Original bar close price (for reference)
        - bar_volume: Original bar volume (for reference)

    Examples
    --------
    >>> from factorexp_backtest.research.utils import run_expression, FactorRequest
    >>>
    >>> request = FactorRequest(
    ...     expression="Clip(ZScore(TS_Std(When(vwap_return, ..., 0), 20), 5760), -2, 2)",
    ...     instrument_id="BTCUSDT.BINANCE",
    ...     start_date="2024-01-01",
    ...     end_date="2024-01-31",
    ...     period=5760
    ... )
    >>>
    >>> result = run_expression(request)
    >>> print(result.head())
    >>> print(f"NaN count: {result['factor_value'].isna().sum()}")
    """
    from pathlib import Path
    from nautilus_trader.persistence.catalog import ParquetDataCatalog

    # Load bars directly from catalog (as Bar objects, not DataFrame)
    from .data_access import get_catalog_path
    print("Loading bar data...", flush=True)

    catalog_path = get_catalog_path()
    print(f"Loading data from catalog at {catalog_path}", flush=True)
    catalog = ParquetDataCatalog(str(catalog_path))
    print(f"Catalog instruments: {catalog.instruments()}", flush=True)

    # Convert instrument_id string to InstrumentId object
    instrument_id_obj = InstrumentId.from_str(request.instrument_id)

    # Load Bar objects from catalog
    print(f"Loading bars for {request.instrument_id} from {request.start_date} to {request.end_date}", flush=True)
    bars = catalog.bars(
        instrument_ids=[instrument_id_obj],
        start=pd.Timestamp(request.start_date),
        end=pd.Timestamp(request.end_date),
    )
    print(f"Loaded {len(bars)} bars", flush=True)

    if not bars:
        raise ValueError(
            f"No data found for {request.instrument_id} between "
            f"{request.start_date} and {request.end_date}"
        )

    # Create indicator
    print("Initializing FactorExpIndicator...", flush=True)
    indicator = FactorExpIndicator(
        expression=request.expression,
    )
    print(f"Initialized FactorExpIndicator with expression: {request.expression}", flush=True)

    # Feed bars and collect results
    results = []

    # add tqdm progress bar for long runs
    from tqdm import tqdm
    for bar in tqdm(
        bars,
        desc="Processing bars",
        unit="bar",
        file=sys.stdout,      # 明确走 stdout
        dynamic_ncols=True,
        mininterval=0,        # 刷新间隔=0
        maxinterval=0,        # 避免内部扩大间隔
        miniters=1,           # 每次迭代都允许刷新
    ):
        # Update indicator with bar
        # print(f"Processing bar at {bar.ts_event}", flush=True)
        indicator.handle_bar(bar)
        # print(f"Indicator value: {indicator.value}", flush=True)

        # Collect result if indicator is ready
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


def evaluate_factor_series(
    expression: str,
    bars_df: pd.DataFrame,
    period: int = 5760,
) -> pd.Series:
    """Simplified evaluation returning only factor values as a Series.

    Parameters
    ----------
    expression : str
        Factor expression string
    bars_df : pd.DataFrame
        Bar data (must have required columns)
    period : int, optional
        Period for ZScore calculation (default: 5760)

    Returns
    -------
    pd.Series
        Factor values indexed by ts_event

    Examples
    --------
    >>> from factorexp_backtest.research.utils import evaluate_factor_series
    >>> from factorexp_backtest.research.utils import load_catalog_bars
    >>>
    >>> bars = load_catalog_bars("BTCUSDT.BINANCE", "2024-01-01", "2024-01-31")
    >>> factor = evaluate_factor_series(
    ...     "ZScore(TS_Std(close, 20), 5760)",
    ...     bars,
    ...     period=5760
    ... )
    >>> print(factor.describe())
    """
    # Create indicator
    indicator = FactorExpIndicator(
        expression=expression,
        period=period,
    )

    # Feed bars and collect values
    timestamps = []
    values = []

    for idx, row in bars_df.iterrows():
        bar = Bar(
            bar_type=row.get("bar_type"),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            ts_event=row["ts_event"],
            ts_init=row["ts_init"],
        )

        indicator.handle_bar(bar)

        if indicator.initialized:
            timestamps.append(row["ts_event"])
            values.append(indicator.value)

    # Create Series with datetime index
    series = pd.Series(
        values,
        index=pd.to_datetime(timestamps, unit="ns"),
        name="factor_value",
    )

    return series
