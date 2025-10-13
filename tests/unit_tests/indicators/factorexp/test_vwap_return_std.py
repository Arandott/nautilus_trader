"""Tests FactorExp expression for VWAP return volatility."""

import statistics
import time

import pytest

from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


pytestmark = pytest.mark.skipif(
    not hasattr(Bar, "amt"),
    reason="extended_bar feature is not enabled in this build",
)


_BAR_TYPE = BarType(
    instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
    bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    aggregation_source=AggregationSource.EXTERNAL,
)

EXPRESSION = (
    "TS_Std("
    "When("
    "Greater(TS_Delta($volume, 1), 0),"
    "Div(Sub(Div($amt, $volume), TS_Ref(Div($amt, $volume), 1)), TS_Ref(Div($amt, $volume), 1)),"
    "Div(0, 0)"
    ")"
    ","
    "96"
    ")"
)


def _make_bar(vwap: float, volume: float) -> Bar:
    now = time.time_ns()
    price_str = f"{vwap:.8f}"
    volume_str = f"{volume:.0f}"
    amt_value = vwap * volume
    return Bar(
        bar_type=_BAR_TYPE,
        open=Price.from_str(price_str),
        high=Price.from_str(price_str),
        low=Price.from_str(price_str),
        close=Price.from_str(price_str),
        volume=Quantity.from_str(volume_str),
        ts_event=now,
        ts_init=now,
        amt=Quantity.from_str(f"{amt_value:.8f}"),
    )


def test_vwap_return_stddev_matches_reference():
    indicator = FactorExpIndicator(EXPRESSION)

    vwap_series = [100.0 + index for index in range(110)]
    volume_series = [1500.0 + index for index in range(110)]
    filtered_returns = []

    for index, (vwap, volume) in enumerate(zip(vwap_series, volume_series)):
        indicator.handle_bar(_make_bar(vwap, volume))

        if index == 0:
            continue

        previous_vwap = vwap_series[index - 1]
        vwap_return = (vwap - previous_vwap) / previous_vwap

        if volume_series[index] - volume_series[index - 1] > 0:
            filtered_returns.append(vwap_return)

    assert indicator.initialized
    assert len(filtered_returns) >= 96

    reference_window = filtered_returns[-96:]
    expected_std = statistics.stdev(reference_window)

    assert indicator.value == pytest.approx(expected_std, rel=1e-9, abs=1e-9)
