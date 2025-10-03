"""Tests for FactorExp extended_bar feature integration."""

import time
import pytest

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.core.nautilus_pyo3 import PriceType


pytestmark = pytest.mark.skipif(
    not hasattr(Bar, "amt"),
    reason="extended_bar feature is not enabled in this build",
)


_BAR_TYPE = BarType(
    instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    aggregation_source=AggregationSource.EXTERNAL,
)


def _make_bar(close_price: float, amt_value: float) -> Bar:
    now = time.time_ns()
    return Bar(
        bar_type=_BAR_TYPE,
        open=Price.from_str(f"{close_price:.2f}"),
        high=Price.from_str(f"{close_price + 0.5:.2f}"),
        low=Price.from_str(f"{close_price - 0.5:.2f}"),
        close=Price.from_str(f"{close_price:.2f}"),
        volume=Quantity.from_str("1000"),
        ts_event=now,
        ts_init=now,
        amt=Quantity.from_str(f"{amt_value:.4f}"),
    )


def test_bar_exposes_extended_amt_quantity():
    bar = _make_bar(100.0, 250.5)
    assert float(bar.amt) == pytest.approx(250.5)


def test_indicator_reads_extended_amt_feature():
    bar = _make_bar(100.0, 512.25)
    indicator = FactorExpIndicator("$amt")

    indicator.handle_bar(bar)

    assert indicator.initialized
    assert indicator.value == pytest.approx(512.25, rel=0, abs=1e-9)


def test_indicator_rolling_mean_of_extended_field():
    indicator = FactorExpIndicator("TS_Mean($amt, 3)")
    values = [100.0, 150.0, 200.0]

    for amt_value in values:
        indicator.handle_bar(_make_bar(99.0, amt_value))

    expected = sum(values) / len(values)
    assert indicator.initialized
    assert indicator.value == pytest.approx(expected, rel=0, abs=1e-9)
