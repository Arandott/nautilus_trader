from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from typing import Sequence
from typing import Tuple
from typing import Type

import pandas as pd

from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import TradeTick
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _to_ns(value: datetime) -> int:
    return pd.Timestamp(value).value


def _intervals_intersect(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return not (a[1] < b[0] or a[0] > b[1])


@dataclass(slots=True)
class WarmupCoverage:
    """Summarizes catalog coverage for a requested warmup window."""

    start_ns: int
    end_ns: int
    missing: list[tuple[int, int]]

    @property
    def covered(self) -> bool:
        return len(self.missing) == 0


class WarmupCatalog:
    """Helper around ParquetDataCatalog for FactorExp warmup persistence."""

    def __init__(
        self,
        base_path: str | Path | None = None,
        update_catalog: bool | None = None,
    ) -> None:
        path = Path(base_path or os.getenv("FACTOREXP_CATALOG_PATH", "./data/catalog")).expanduser()
        path.mkdir(parents=True, exist_ok=True)

        self._path = path
        self._catalog = ParquetDataCatalog(str(path))
        self._update_enabled = (
            _env_bool("WARMUP_UPDATE_CATALOG", True) if update_catalog is None else update_catalog
        )

    @property
    def path(self) -> Path:
        return self._path

    @property
    def catalog(self) -> ParquetDataCatalog:
        return self._catalog

    @property
    def update_enabled(self) -> bool:
        return self._update_enabled

    def summarize_bar_coverage(
        self,
        bar_type: BarType,
        start: datetime,
        end: datetime,
    ) -> WarmupCoverage:
        start_ns = _to_ns(start)
        end_ns = _to_ns(end)
        missing = self._catalog.get_missing_intervals_for_request(
            start_ns,
            end_ns,
            Bar,
            str(bar_type),
        )
        return WarmupCoverage(start_ns=start_ns, end_ns=end_ns, missing=missing)

    def query_bars(
        self,
        bar_type: BarType,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        bars = self._catalog.query(
            data_cls=Bar,
            identifiers=[str(bar_type)],
            start=start,
            end=end,
        )
        return sorted(bars, key=lambda bar: bar.ts_init)

    def write_data(
        self,
        data: Sequence[object],
        *,
        data_cls: Type[object] | None = None,
        skip_if_present: bool = True,
    ) -> bool:
        if not data or not self._update_enabled:
            return False

        data_cls = data_cls or type(data[0])
        identifier = self._resolve_identifier(data[0])
        start_ts = data[0].ts_init
        end_ts = data[-1].ts_init

        if skip_if_present:
            missing = self._catalog.get_missing_intervals_for_request(
                start_ts,
                end_ts,
                data_cls,
                identifier,
            )
            chunk_interval = (start_ts, end_ts)
            if not any(_intervals_intersect(chunk_interval, interval) for interval in missing):
                return False

        self._catalog.write_data(list(data), start=start_ts, end=end_ts)
        return True

    def _resolve_identifier(self, datum: object) -> str:
        if isinstance(datum, Bar):
            return str(datum.bar_type)
        if isinstance(datum, TradeTick):
            return datum.instrument_id.value
        if hasattr(datum, "instrument_id"):
            return datum.instrument_id.value
        raise TypeError(f"Unsupported data type for catalog persistence: {type(datum).__name__}")

    def ensure_directory(self) -> None:
        self._path.mkdir(parents=True, exist_ok=True)

    def iter_missing_chunks(
        self,
        data_cls: Type[object],
        identifier: str,
        start: datetime,
        end: datetime,
    ) -> Iterable[tuple[int, int]]:
        start_ns = _to_ns(start)
        end_ns = _to_ns(end)
        missing = self._catalog.get_missing_intervals_for_request(
            start_ns,
            end_ns,
            data_cls,
            identifier,
        )
        yield from missing
