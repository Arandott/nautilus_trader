from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pandas as pd
import pytest

from factorexp_live_trading.components.warmup_catalog import WarmupCatalog
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider


def _make_bar_series(bar_type: BarType, start_ns: int, count: int, step_seconds: int) -> list[Bar]:
    bars: list[Bar] = []
    step_ns = step_seconds * 1_000_000_000

    for index in range(count):
        ts = start_ns + index * step_ns
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price.from_str("1500.00"),
                high=Price.from_str("1501.00"),
                low=Price.from_str("1499.00"),
                close=Price.from_str("1500.50"),
                volume=Quantity.from_int(10),
                ts_event=ts,
                ts_init=ts,
            )
        )

    return bars


@pytest.mark.parametrize("minutes", [3])
def test_warmup_catalog_reports_and_fills_missing_ranges(tmp_path, minutes):
    base_path = tmp_path / "catalog"
    catalog = WarmupCatalog(base_path=base_path, update_catalog=True)

    instrument = TestInstrumentProvider.ethusdt_perp_binance()
    bar_spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    bar_type = BarType(instrument.id, bar_spec)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=minutes - 1)
    start_ns = pd.Timestamp(start).value
    end_ns = pd.Timestamp(end).value

    coverage = catalog.summarize_bar_coverage(bar_type, start, end)
    assert not coverage.covered
    assert coverage.missing == [(start_ns, end_ns)]

    bars = _make_bar_series(bar_type, start_ns, minutes, step_seconds=60)
    assert catalog.write_data(bars) is True

    coverage_after = catalog.summarize_bar_coverage(bar_type, start, end)
    assert coverage_after.covered
    assert coverage_after.missing == []

    # Second write should be a no-op due to idempotent guard
    assert catalog.write_data(bars) is False
