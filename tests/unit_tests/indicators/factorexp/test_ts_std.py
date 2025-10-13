"""
Test cases for TS_Std (rolling standard deviation) operator in FactorExp.

Tests the TS_Std operator functionality through actual data processing,
ensuring correct statistical calculations aligned with Python's statistics.stdev().
"""

import math
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


class TestTsStd:
    """Test cases for the TS_Std operator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )

    def create_bar(
        self,
        close: float,
        high: float = None,
        low: float = None,
        volume: float = 1000.0,
        open_price: float = None,
    ) -> Bar:
        """Create a test bar with specified values."""
        if open_price is None:
            open_price = close

        # If high/low not specified, calculate them
        if high is None:
            high = max(open_price, close) + 1.0
        if low is None:
            low = min(open_price, close) - 1.0

        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{open_price:.8f}"),
            high=Price.from_str(f"{high:.8f}"),
            low=Price.from_str(f"{low:.8f}"),
            close=Price.from_str(f"{close:.8f}"),
            volume=Quantity.from_str(f"{volume:.0f}"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )

    def test_ts_std_basic_calculation(self):
        """Test basic TS_Std calculation matches Python statistics.stdev()."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed known values: [100, 102, 104, 106, 108]
        test_values = [100.0, 102.0, 104.0, 106.0, 108.0]

        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # After 5 values, indicator should be initialized
        assert indicator.initialized, "Indicator should be initialized after window_size bars"

        # Calculate reference using Python statistics
        # Python's stdev() uses ddof=1 (sample standard deviation)
        expected_std = statistics.stdev(test_values)

        # Compare with tight tolerance
        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected {expected_std}, got {indicator.value}"

    def test_ts_std_window_initialization(self):
        """Test TS_Std initialization behavior before window is full."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed fewer values than window size
        for i in range(window - 1):
            bar = self.create_bar(100.0 + i)
            indicator.handle_bar(bar)
            assert not indicator.initialized, f"Should not be initialized at bar {i + 1}"

        # Feed the last value to complete window
        bar = self.create_bar(100.0 + window - 1)
        indicator.handle_bar(bar)
        assert indicator.initialized, "Should be initialized after window_size bars"
        assert not math.isnan(indicator.value), "Should have valid value after initialization"

    def test_ts_std_window_rolling(self):
        """Test TS_Std correctly implements rolling window (old values drop out)."""
        window = 3
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed sequence: [100, 110, 120, 130, 140]
        sequence = [100.0, 110.0, 120.0, 130.0, 140.0]
        for value in sequence:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # After 5 bars, window should contain last 3: [120, 130, 140]
        expected_window = sequence[-window:]
        expected_std = statistics.stdev(expected_window)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected std of {expected_window} = {expected_std}, got {indicator.value}"

    def test_ts_std_constant_values(self):
        """Test TS_Std returns 0 for constant values (zero variance)."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed constant value
        constant_value = 100.0
        for _ in range(window):
            bar = self.create_bar(constant_value)
            indicator.handle_bar(bar)

        # Standard deviation of constant values should be 0
        assert indicator.value == pytest.approx(
            0.0, abs=1e-9
        ), f"Expected 0.0 for constant values, got {indicator.value}"

    def test_ts_std_single_outlier(self):
        """Test TS_Std correctly reflects impact of single outlier."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed values with one outlier: [100, 100, 100, 100, 200]
        normal_value = 100.0
        outlier_value = 200.0

        for _ in range(window - 1):
            bar = self.create_bar(normal_value)
            indicator.handle_bar(bar)

        bar = self.create_bar(outlier_value)
        indicator.handle_bar(bar)

        # Calculate expected std with outlier
        test_values = [normal_value] * (window - 1) + [outlier_value]
        expected_std = statistics.stdev(test_values)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected {expected_std} with outlier, got {indicator.value}"

        # Verify std is higher than for constant values
        assert indicator.value > 0.0, "Std should be > 0 when outlier present"

    def test_ts_std_precision(self):
        """Test TS_Std numerical stability with large values."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Use large values to test numerical precision
        base_value = 1_000_000.0
        test_values = [base_value + i * 100 for i in range(window)]

        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        expected_std = statistics.stdev(test_values)

        # Use relative tolerance for large numbers
        assert indicator.value == pytest.approx(
            expected_std, rel=1e-6
        ), f"Expected {expected_std}, got {indicator.value}"

    def test_ts_std_small_window(self):
        """Test TS_Std with minimum window size of 2."""
        window = 2
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed exactly 2 values
        values = [100.0, 110.0]
        for value in values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        expected_std = statistics.stdev(values)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected {expected_std} for window=2, got {indicator.value}"

    def test_ts_std_increasing_sequence(self):
        """Test TS_Std with strictly increasing sequence."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Strictly increasing: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for value in range(1, 11):
            bar = self.create_bar(float(value))
            indicator.handle_bar(bar)

        # Last window: [6, 7, 8, 9, 10]
        expected_window = list(range(6, 11))
        expected_std = statistics.stdev(expected_window)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected std of {expected_window} = {expected_std}, got {indicator.value}"

    def test_ts_std_decreasing_sequence(self):
        """Test TS_Std with strictly decreasing sequence."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Strictly decreasing: [100, 90, 80, 70, 60, 50, 40, 30]
        sequence = [100.0 - i * 10 for i in range(8)]
        for value in sequence:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Last window: [60, 50, 40, 30] (indices -4 to -1)
        expected_window = sequence[-window:]
        expected_std = statistics.stdev(expected_window)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected std of {expected_window} = {expected_std}, got {indicator.value}"

    def test_ts_std_alternating_values(self):
        """Test TS_Std with alternating high/low values."""
        window = 6
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Alternating: [100, 200, 100, 200, 100, 200]
        for i in range(window):
            value = 100.0 if i % 2 == 0 else 200.0
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Calculate expected std for alternating pattern
        test_values = [100.0, 200.0, 100.0, 200.0, 100.0, 200.0]
        expected_std = statistics.stdev(test_values)

        assert indicator.value == pytest.approx(
            expected_std, rel=1e-9, abs=1e-9
        ), f"Expected {expected_std} for alternating values, got {indicator.value}"

    def test_ts_std_in_composite_expression(self):
        """Test TS_Std as part of a composite expression (Bollinger Band width)."""
        # Bollinger Band width: 2 * TS_Std($close, 20)
        window = 20
        indicator = FactorExpIndicator(f"Mul(2, TS_Std($close, {window}))")

        # Feed simple increasing sequence
        test_values = [100.0 + i for i in range(window + 5)]
        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Last window
        expected_window = test_values[-window:]
        expected_std = statistics.stdev(expected_window)
        expected_bb_width = 2 * expected_std

        assert indicator.value == pytest.approx(
            expected_bb_width, rel=1e-9, abs=1e-9
        ), f"Expected 2*{expected_std} = {expected_bb_width}, got {indicator.value}"

    def test_ts_std_with_division(self):
        """Test TS_Std in division expression (coefficient of variation)."""
        # Coefficient of variation: TS_Std($close, 10) / TS_Mean($close, 10)
        window = 10
        indicator = FactorExpIndicator(
            f"Div(TS_Std($close, {window}), TS_Mean($close, {window}))"
        )

        # Feed known values
        test_values = [100.0 + i * 5 for i in range(window)]
        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Calculate expected coefficient of variation
        expected_std = statistics.stdev(test_values)
        expected_mean = statistics.mean(test_values)
        expected_cv = expected_std / expected_mean

        assert indicator.value == pytest.approx(
            expected_cv, rel=1e-6
        ), f"Expected CV = {expected_cv}, got {indicator.value}"


if __name__ == "__main__":
    """Run tests locally for development."""
    test = TestTsStd()

    print("=" * 80)
    print("TS_Std Operator Test Suite")
    print("=" * 80)

    test_methods = [
        ("Basic Calculation", test.test_ts_std_basic_calculation),
        ("Window Initialization", test.test_ts_std_window_initialization),
        ("Rolling Window", test.test_ts_std_window_rolling),
        ("Constant Values", test.test_ts_std_constant_values),
        ("Single Outlier", test.test_ts_std_single_outlier),
        ("Numerical Precision", test.test_ts_std_precision),
        ("Small Window", test.test_ts_std_small_window),
        ("Increasing Sequence", test.test_ts_std_increasing_sequence),
        ("Decreasing Sequence", test.test_ts_std_decreasing_sequence),
        ("Alternating Values", test.test_ts_std_alternating_values),
        ("Composite Expression", test.test_ts_std_in_composite_expression),
        ("Division Expression", test.test_ts_std_with_division),
    ]

    passed = 0
    failed = 0

    for test_name, test_method in test_methods:
        print(f"\n[{passed + failed + 1}/{len(test_methods)}] Running: {test_name}...", end=" ")
        try:
            test.setup_method()
            test_method()
            print("✅ PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {e}")
            failed += 1

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed")
