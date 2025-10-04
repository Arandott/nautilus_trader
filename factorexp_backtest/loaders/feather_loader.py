"""
Feather file loader with extended bar support for factor backtesting.

This loader reads feather files containing OHLCV + amt (成交额) data
and creates Nautilus Bar objects. When the extended_bar feature is enabled
in Rust, it can set the amt field on bars.
"""

import warnings
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.feather as feather

from nautilus_trader.core.nautilus_pyo3 import AggregationSource
from nautilus_trader.core.nautilus_pyo3 import Bar
from nautilus_trader.core.nautilus_pyo3 import BarAggregation
from nautilus_trader.core.nautilus_pyo3 import BarSpecification
from nautilus_trader.core.nautilus_pyo3 import BarType
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


class FeatherBarLoader:
    """
    Load bars with extended fields from feather files.

    This loader handles feather files with the following expected columns:
    - Standard: open, high, low, close, volume, ts_event
    - Extended: amt (成交额), vwap, bid_volume, ask_volume, etc.

    The extended fields are only set if the Rust extended_bar feature is enabled.
    """

    def __init__(self, data_dir: Path):
        """
        Initialize the loader.

        Parameters
        ----------
        data_dir : Path
            Directory containing feather files.
        """
        self.data_dir = Path(data_dir)
        self._has_extended_bar = self._check_extended_bar()

        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

    @staticmethod
    def _check_extended_bar() -> bool:
        """Check if extended bar feature is available."""
        return bool(EXTENDED_BAR_FIELD_SPECS)

    def load_bars(
        self,
        instrument_id: InstrumentId,
        start_date: pd.Timestamp | None = None,
        end_date: pd.Timestamp | None = None,
        bar_spec: BarSpecification | None = None,
        field_mappings: dict[str, str] | None = None,
    ) -> list[Bar]:
        """
        Load bars for an instrument from feather files.

        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to load.
        start_date : pd.Timestamp, optional
            Start date filter.
        end_date : pd.Timestamp, optional
            End date filter.
        bar_spec : BarSpecification, optional
            Bar specification. Defaults to 1-MINUTE-LAST.
        field_mappings : Dict[str, str], optional
            Custom field name mappings (e.g., {'turnover_amount': 'amt'}).

        Returns
        -------
        List[Bar]
            Loaded bars with extended fields if available.
        """
        # Default bar specification
        if bar_spec is None:
            bar_spec = BarSpecification(
                step=1,
                aggregation=BarAggregation.MINUTE,
                price_type=PriceType.LAST,
            )

        # Find data file
        symbol = instrument_id.symbol.value
        filepath = self._find_data_file(symbol)

        if not filepath.exists():
            raise FileNotFoundError(f"Data file not found for {symbol}")

        # Load dataframe
        df = self._load_feather(filepath)

        # Apply field mappings if provided
        if field_mappings:
            df = df.rename(columns=field_mappings)

        # Apply date filters
        if start_date:
            df = df[df["ts_event"] >= start_date.value]
        if end_date:
            df = df[df["ts_event"] <= end_date.value]

        # Create bars
        bars = self._create_bars(df, instrument_id, bar_spec)

        return bars

    def _find_data_file(self, symbol: str) -> Path:
        """Find the feather file for a symbol."""
        # Try exact match first
        exact_path = self.data_dir / f"{symbol}.feather"
        if exact_path.exists():
            return exact_path

        # Try with .fea extension
        fea_path = self.data_dir / f"{symbol}.fea"
        if fea_path.exists():
            return fea_path

        # Try pattern matching
        pattern = f"*{symbol}*.feather"
        matches = list(self.data_dir.glob(pattern))
        if matches:
            return matches[0]

        # Try .fea pattern
        pattern = f"*{symbol}*.fea"
        matches = list(self.data_dir.glob(pattern))
        if matches:
            return matches[0]

        raise FileNotFoundError(f"No data file found for {symbol}")

    def _load_feather(self, filepath: Path) -> pd.DataFrame:
        """Load feather file into DataFrame."""
        try:
            # Try pyarrow feather reader
            df = feather.read_feather(filepath)
        except Exception:
            # Fallback to pandas
            try:
                df = pd.read_feather(filepath)
            except Exception as e2:
                raise RuntimeError(f"Failed to load feather file {filepath}: {e2}")

        # Ensure required columns exist
        required_columns = ["open", "high", "low", "close", "volume"]
        missing = set(required_columns) - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Check for timestamp column (might be named differently)
        if "ts_event" not in df.columns:
            if "timestamp" in df.columns:
                df["ts_event"] = df["timestamp"]
            elif "time" in df.columns:
                df["ts_event"] = df["time"]
            elif "datetime" in df.columns:
                df["ts_event"] = df["datetime"]
            else:
                # Use index if it's a datetime index
                if isinstance(df.index, pd.DatetimeIndex):
                    df["ts_event"] = df.index
                else:
                    raise ValueError("No timestamp column found")

        # Convert timestamp to nanoseconds if needed
        if pd.api.types.is_datetime64_any_dtype(df["ts_event"]):
            df["ts_event"] = df["ts_event"].astype("int64")

        return df

    def _create_bars(
        self,
        df: pd.DataFrame,
        instrument_id: InstrumentId,
        bar_spec: BarSpecification,
    ) -> list[Bar]:
        """Create Bar objects from DataFrame."""
        bars = []

        # Create bar type
        bar_type = BarType(
            instrument_id=instrument_id,
            spec=bar_spec,
            aggregation_source=AggregationSource.EXTERNAL,
        )

        # Identify available extended fields
        extended_specs = [
            spec for spec in EXTENDED_BAR_FIELD_SPECS if spec["name"] in df.columns
        ]

        if extended_specs and not self._has_extended_bar:
            warnings.warn(
                f"Extended fields found ({', '.join(spec['name'] for spec in extended_specs)}) "
                "but extended_bar feature not enabled. These fields will be ignored.",
                RuntimeWarning
            )

        # Create bars
        for _, row in df.iterrows():
            # Create base bar
            kwargs: dict[str, Any] = {}

            if self._has_extended_bar:
                for spec in extended_specs:
                    value = row[spec["name"]]
                    if pd.notna(value):
                        kwargs[spec["name"]] = self._convert_extended_value(spec, value)

            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(str(row["open"])),
                high=Price.from_str(str(row["high"])),
                low=Price.from_str(str(row["low"])),
                close=Price.from_str(str(row["close"])),
                volume=Quantity.from_str(str(row["volume"])),
                ts_event=int(row["ts_event"]),
                ts_init=int(row.get("ts_init", row["ts_event"])),
                **kwargs,
            )

            bars.append(bar)

        print(f"Loaded {len(bars)} bars for {instrument_id}")
        if extended_specs:
            print(
                "  Extended fields: "
                + ", ".join(spec["name"] for spec in extended_specs)
            )

        return bars

    @staticmethod
    def _convert_extended_value(spec: dict[str, Any], raw: Any) -> Any:
        field_type = spec["type"]
        if field_type == "quantity":
            return Quantity.from_str(str(raw)) if not isinstance(raw, Quantity) else raw
        if field_type == "price":
            return Price.from_str(str(raw)) if not isinstance(raw, Price) else raw
        if field_type == "u64":
            return int(raw)
        if field_type == "bool":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(int(raw))
            lowered = str(raw).strip().lower()
            return lowered in {"true", "1", "yes", "y", "t"}
        raise ValueError(f"Unsupported extended field type '{field_type}'")

    def get_available_instruments(self) -> list[str]:
        """Get list of available instruments in data directory."""
        feather_files = list(self.data_dir.glob("*.feather")) + list(self.data_dir.glob("*.fea"))
        instruments = []

        for f in feather_files:
            # Remove extension and any date suffixes
            name = f.stem
            # Handle files like "BTCUSDT_2023-03-29.feather"
            if "_" in name:
                name = name.split("_")[0]
            instruments.append(name)

        return sorted(set(instruments))

    def load_multi_day_bars(
        self,
        instrument_id: InstrumentId,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        bar_spec: BarSpecification | None = None,
    ) -> list[Bar]:
        """
        Load bars from multiple daily feather files.

        This method handles the case where data is split into daily files
        like 2023-03-29.fea, 2023-03-30.fea, etc.
        """
        all_bars = []

        # Generate date range
        date_range = pd.date_range(start_date.date(), end_date.date(), freq="D")

        for date in date_range:
            date_str = date.strftime("%Y-%m-%d")

            # Try to find file for this date
            date_file = self.data_dir / f"{date_str}.fea"
            if not date_file.exists():
                date_file = self.data_dir / f"{date_str}.feather"

            if date_file.exists():
                try:
                    df = self._load_feather(date_file)

                    # Filter for the specific instrument if multiple instruments in file
                    if "symbol" in df.columns:
                        symbol = instrument_id.symbol.value
                        df = df[df["symbol"] == symbol]

                    if not df.empty:
                        bars = self._create_bars(df, instrument_id, bar_spec or BarSpecification(
                            step=1,
                            aggregation=BarAggregation.MINUTE,
                            price_type=PriceType.LAST,
                        ))
                        all_bars.extend(bars)
                        print(f"  Loaded {len(bars)} bars from {date_str}")

                except Exception as e:
                    warnings.warn(f"Failed to load {date_file}: {e}")

        return all_bars
