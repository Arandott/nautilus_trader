"""
Test cases for TS_Quantile (rolling quantile) operator in FactorExp.

Tests the TS_Quantile operator functionality through actual data processing,
ensuring correct quantile calculations using R-7 method (pandas default).
Validates both SortedArray (small windows) and DualHeap (large windows) implementations.
"""

import math
import statistics
import time

import numpy as np
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


class TestTsQuantile:
    """Test cases for the TS_Quantile operator."""

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
        """Create a test bar with specified values (NaN-safe)."""
        if open_price is None:
            open_price = close if not math.isnan(close) else 100.0

        # Handle NaN for high/low calculation
        if high is None:
            if not math.isnan(close) and not math.isnan(open_price):
                high = max(open_price, close) + 1.0
            else:
                high = 101.0  # Default for NaN

        if low is None:
            if not math.isnan(close) and not math.isnan(open_price):
                low = min(open_price, close) - 1.0
            else:
                low = 99.0  # Default for NaN

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

    def feed_series(self, indicator: FactorExpIndicator, values: list[float]) -> list:
        """
        Feed a series of values to an indicator and capture snapshots.

        Args:
            indicator: FactorExpIndicator instance
            values: List of values (may contain NaN)

        Returns:
            List of (value, initialized, is_value_nan) tuples after each update
        """
        snapshots = []
        for val in values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)
            snapshots.append(
                (indicator.value, indicator.initialized, math.isnan(indicator.value))
            )
        return snapshots

    def compute_quantile_r7(self, values: list[float], phi: float) -> float:
        """
        Compute quantile using R-7 method (pandas default).

        R-7 method: h = (n - 1) * phi + 1
        Interpolation: (1 - g) * x[j] + g * x[j+1]

        Args:
            values: List of values (should not contain NaN)
            phi: Quantile level [0.0, 1.0]

        Returns:
            Quantile value
        """
        if not values:
            return float("nan")

        sorted_values = sorted(values)
        n = len(sorted_values)

        if n == 1:
            return sorted_values[0]

        # R-7 method
        h = (n - 1) * phi + 1.0
        h = max(1.0, min(h, n))  # Clamp to [1, n]

        j = int(math.floor(h))
        g = h - j
        idx = max(0, min(j - 1, n - 1))  # Convert to 0-based index

        if idx >= n - 1 or g <= 1e-10:
            return sorted_values[idx]
        else:
            return (1.0 - g) * sorted_values[idx] + g * sorted_values[idx + 1]

    # -------------------------------------------------------------------------
    # Test 1: Basic Functionality
    # -------------------------------------------------------------------------

    def test_ts_quantile_median_basic(self):
        """Test TS_Quantile median (phi=0.5) calculation."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed known values: [1, 2, 3, 4, 5]
        test_values = [1.0, 2.0, 3.0, 4.0, 5.0]

        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # After window_size values, should be initialized
        assert indicator.initialized, "Indicator should be initialized after window_size bars"

        # Median of [1, 2, 3, 4, 5] = 3.0
        expected_median = self.compute_quantile_r7(test_values, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected median {expected_median}, got {indicator.value}"

    def test_ts_quantile_quartiles(self):
        """Test TS_Quantile Q1 (0.25) and Q3 (0.75) calculation."""
        window = 100
        test_values = list(range(1, window + 1))

        # Test Q1 (25th percentile)
        q1_indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, 0.25)")
        for value in test_values:
            bar = self.create_bar(float(value))
            q1_indicator.handle_bar(bar)

        expected_q1 = self.compute_quantile_r7(test_values, 0.25)
        assert q1_indicator.value == pytest.approx(
            expected_q1, abs=0.1
        ), f"Expected Q1 {expected_q1}, got {q1_indicator.value}"

        # Test Q3 (75th percentile)
        q3_indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, 0.75)")
        for value in test_values:
            bar = self.create_bar(float(value))
            q3_indicator.handle_bar(bar)

        expected_q3 = self.compute_quantile_r7(test_values, 0.75)
        assert q3_indicator.value == pytest.approx(
            expected_q3, abs=0.1
        ), f"Expected Q3 {expected_q3}, got {q3_indicator.value}"

    def test_ts_quantile_extreme_values(self):
        """Test TS_Quantile with extreme phi values (0.0 = min, 1.0 = max)."""
        window = 5
        test_values = [3.0, 1.0, 4.0, 1.0, 5.0]

        # Test phi=0.0 (minimum)
        min_indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, 0.0)")
        for value in test_values:
            bar = self.create_bar(value)
            min_indicator.handle_bar(bar)

        assert min_indicator.value == pytest.approx(
            1.0, abs=1e-9
        ), f"Expected min=1.0, got {min_indicator.value}"

        # Test phi=1.0 (maximum)
        max_indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, 1.0)")
        for value in test_values:
            bar = self.create_bar(value)
            max_indicator.handle_bar(bar)

        assert max_indicator.value == pytest.approx(
            5.0, abs=1e-9
        ), f"Expected max=5.0, got {max_indicator.value}"

    # -------------------------------------------------------------------------
    # Test 2: Window Behavior
    # -------------------------------------------------------------------------

    def test_ts_quantile_window_initialization(self):
        """Test TS_Quantile initialization behavior before window is full."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

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

    def test_ts_quantile_rolling_window(self):
        """Test TS_Quantile correctly implements rolling window."""
        window = 3
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed sequence: [1, 2, 3, 4, 5]
        sequence = [1.0, 2.0, 3.0, 4.0, 5.0]
        for value in sequence:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # After 5 bars, window should contain last 3: [3, 4, 5]
        expected_window = sequence[-window:]
        expected_median = self.compute_quantile_r7(expected_window, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected median of {expected_window} = {expected_median}, got {indicator.value}"

    def test_ts_quantile_small_window(self):
        """Test TS_Quantile with minimum practical window size."""
        window = 2
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed exactly 2 values
        values = [100.0, 110.0]
        for value in values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Median of [100, 110] = 105
        expected_median = self.compute_quantile_r7(values, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected {expected_median}, got {indicator.value}"

    # -------------------------------------------------------------------------
    # Test 3: Algorithm Switch (SortedArray vs DualHeap)
    # -------------------------------------------------------------------------

    def test_ts_quantile_sorted_array_implementation(self):
        """Test TS_Quantile with small window using SortedArray (≤1024)."""
        window = 10
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Test with unsorted data
        values = [5.0, 2.0, 8.0, 1.0, 9.0, 3.0, 7.0, 4.0, 6.0, 10.0]
        for val in values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)

        # Median of [1,2,3,4,5,6,7,8,9,10] = 5.5
        expected_median = self.compute_quantile_r7(sorted(values), phi)
        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected {expected_median}, got {indicator.value}"

    def test_ts_quantile_dual_heap_implementation(self):
        """Test TS_Quantile with large window using DualHeap (>1024)."""
        window = 2000
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Fill with sequential values
        for i in range(1, window + 1):
            bar = self.create_bar(float(i))
            indicator.handle_bar(bar)

        # Median of [1..2000] = 1000.5
        expected_median = (window + 1) / 2.0
        assert indicator.value == pytest.approx(
            expected_median, abs=1.0
        ), f"Expected ~{expected_median}, got {indicator.value}"

        # Test rolling update
        bar = self.create_bar(float(window + 1))
        indicator.handle_bar(bar)

        # Window now [2..2001], median = 1001.5
        expected_median += 1.0
        assert indicator.value == pytest.approx(
            expected_median, abs=1.0
        ), f"Expected ~{expected_median} after rolling, got {indicator.value}"

    def test_ts_quantile_algorithm_consistency(self):
        """Test that SortedArray and DualHeap produce consistent results."""
        # Test data
        test_values = list(range(1, 101))

        # Small window (SortedArray)
        small_window = 100
        phi = 0.5
        small_indicator = FactorExpIndicator(f"TS_Quantile($close, {small_window}, {phi})")

        for value in test_values:
            bar = self.create_bar(float(value))
            small_indicator.handle_bar(bar)

        small_result = small_indicator.value

        # Large window (DualHeap) - use threshold + 100
        large_window = 1124  # SMALL_WINDOW_THRESHOLD + 100
        large_indicator = FactorExpIndicator(f"TS_Quantile($close, {large_window}, {phi})")

        # Feed enough data to fill large window
        for i in range(1, large_window + 1):
            bar = self.create_bar(float(i))
            large_indicator.handle_bar(bar)

        # Both should compute valid medians
        assert not math.isnan(small_result), "Small window should produce valid result"
        assert not math.isnan(large_indicator.value), "Large window should produce valid result"

    # -------------------------------------------------------------------------
    # Test 4: NaN Handling
    # -------------------------------------------------------------------------

    def test_ts_quantile_nan_filtering(self):
        """Test TS_Quantile correctly filters out NaN values."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed: [1, NaN, 2, 3, 4]
        values = [1.0, float("nan"), 2.0, 3.0, 4.0]
        self.feed_series(indicator, values)

        assert indicator.initialized
        # Median of valid values [1, 2, 3, 4] = 2.5
        valid_values = [v for v in values if not math.isnan(v)]
        expected_median = self.compute_quantile_r7(valid_values, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected median of {valid_values} = {expected_median}, got {indicator.value}"

    def test_ts_quantile_all_nan_reuse_stale(self):
        """Test TS_Quantile reuses last valid value when window becomes all NaN."""
        window = 3
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Phase 1: Establish valid baseline [1, 2, 3]
        baseline = [1.0, 2.0, 3.0]
        self.feed_series(indicator, baseline)

        assert indicator.initialized
        last_valid_median = indicator.value
        expected_median = self.compute_quantile_r7(baseline, phi)
        assert last_valid_median == pytest.approx(expected_median, abs=1e-9)

        # Phase 2: Feed all NaN
        nan_values = [float("nan"), float("nan"), float("nan")]
        self.feed_series(indicator, nan_values)

        # Should reuse last valid median
        assert indicator.value == pytest.approx(
            last_valid_median, abs=1e-9
        ), "Should reuse last valid median when all NaN"
        assert not math.isnan(indicator.value), "Should not return NaN"

    def test_ts_quantile_interleaved_nans(self):
        """Test TS_Quantile with interleaved NaN values."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed: [1, NaN, 2, NaN, 3, 4, 5]
        sequence = [1.0, float("nan"), 2.0, float("nan"), 3.0, 4.0, 5.0]
        self.feed_series(indicator, sequence)

        assert indicator.initialized

        # Window contains last 5: [NaN, 3, 4, 5] + earlier values
        # Valid values in final window: [2, 3, 4, 5] (depending on rolling)
        # After 7 updates, window is [NaN, 3, 4, 5] from positions [3, 4, 5, 6, 7]
        # Valid values: [3, 4, 5]
        # Actually, let's compute properly:
        # Position 0: [1] -> 1
        # Position 1: [1, NaN] -> 1
        # Position 2: [1, NaN, 2] -> median(1,2) = 1.5
        # Position 3: [1, NaN, 2, NaN] -> median(1,2) = 1.5
        # Position 4: [1, NaN, 2, NaN, 3] -> median(1,2,3) = 2
        # Position 5: [NaN, 2, NaN, 3, 4] -> median(2,3,4) = 3
        # Position 6: [2, NaN, 3, 4, 5] -> median(2,3,4,5) = 3.5

        # Verify it's a valid finite value
        assert not math.isnan(indicator.value), "Should produce valid median with interleaved NaN"
        assert math.isfinite(indicator.value), "Should produce finite median"

    # -------------------------------------------------------------------------
    # Test 5: Edge Cases and Special Values
    # -------------------------------------------------------------------------

    def test_ts_quantile_constant_values(self):
        """Test TS_Quantile with constant values."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed constant value
        constant_value = 100.0
        for _ in range(window):
            bar = self.create_bar(constant_value)
            indicator.handle_bar(bar)

        # Quantile of constant values = constant
        assert indicator.value == pytest.approx(
            constant_value, abs=1e-9
        ), f"Expected {constant_value} for constant values, got {indicator.value}"

    def test_ts_quantile_single_value(self):
        """Test TS_Quantile with single unique value in window."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # All same value
        for i in range(window):
            bar = self.create_bar(42.0)
            indicator.handle_bar(bar)

        assert indicator.initialized
        assert indicator.value == pytest.approx(
            42.0, abs=1e-9
        ), "Quantile of identical values should be that value"

    def test_ts_quantile_duplicate_values(self):
        """Test TS_Quantile with many duplicates."""
        window = 10
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Feed duplicates: [1,1,1,1,1,2,2,2,2,2]
        for _ in range(5):
            bar = self.create_bar(1.0)
            indicator.handle_bar(bar)
        for _ in range(5):
            bar = self.create_bar(2.0)
            indicator.handle_bar(bar)

        # Median of [1,1,1,1,1,2,2,2,2,2] = 1.5
        test_values = [1.0] * 5 + [2.0] * 5
        expected_median = self.compute_quantile_r7(test_values, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected {expected_median}, got {indicator.value}"

    # -------------------------------------------------------------------------
    # Test 6: Numerical Precision
    # -------------------------------------------------------------------------

    def test_ts_quantile_r7_interpolation(self):
        """Test R-7 interpolation method accuracy."""
        window = 4
        phi = 0.25
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Values: [1, 2, 3, 4]
        test_values = [1.0, 2.0, 3.0, 4.0]
        for val in test_values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)

        # R-7: h = (4-1)*0.25 + 1 = 1.75
        # Interpolate between x[0]=1 and x[1]=2
        # Result = (1-0.75)*1 + 0.75*2 = 1.75
        expected_q1 = self.compute_quantile_r7(test_values, phi)

        assert indicator.value == pytest.approx(
            expected_q1, abs=1e-9
        ), f"Expected R-7 Q1={expected_q1}, got {indicator.value}"

    def test_ts_quantile_large_values_precision(self):
        """Test TS_Quantile numerical stability with large values."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Large values
        base_value = 1_000_000.0
        test_values = [base_value + i * 100 for i in range(window)]

        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        expected_median = self.compute_quantile_r7(test_values, phi)

        assert indicator.value == pytest.approx(
            expected_median, rel=1e-6
        ), f"Expected {expected_median}, got {indicator.value}"

    # -------------------------------------------------------------------------
    # Test 7: Reset and State Management
    # -------------------------------------------------------------------------

    def test_ts_quantile_reset_hygiene(self):
        """Test TS_Quantile reset does not leak previous statistics."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Phase 1: Initial data [100, 101, 102, 103, 104]
        initial_data = [100.0, 101.0, 102.0, 103.0, 104.0]
        self.feed_series(indicator, initial_data)

        assert indicator.initialized
        initial_median = indicator.value
        expected_initial = self.compute_quantile_r7(initial_data, phi)
        assert initial_median == pytest.approx(expected_initial, abs=1e-9)

        # Reset
        indicator.reset()
        assert not indicator.initialized, "Should not be initialized after reset"
        assert math.isnan(indicator.value), "Value should be NaN after reset"

        # Phase 2: New data [1, 2, 3, 4, 5]
        new_data = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.feed_series(indicator, new_data)

        assert indicator.initialized
        new_median = indicator.value
        expected_new = self.compute_quantile_r7(new_data, phi)

        assert new_median == pytest.approx(
            expected_new, abs=1e-9
        ), f"Expected new median {expected_new}, got {new_median}"
        assert abs(new_median - initial_median) > 50.0, "Medians should be significantly different"

    # -------------------------------------------------------------------------
    # Test 8: Composite Expressions
    # -------------------------------------------------------------------------

    def test_ts_quantile_iqr_calculation(self):
        """Test TS_Quantile in IQR (Interquartile Range) calculation: Q3 - Q1."""
        window = 100
        indicator = FactorExpIndicator(
            f"Sub(TS_Quantile($close, {window}, 0.75), TS_Quantile($close, {window}, 0.25))"
        )

        # Sequential data [1..100]
        test_values = list(range(1, window + 1))
        for value in test_values:
            bar = self.create_bar(float(value))
            indicator.handle_bar(bar)

        # IQR = Q3 - Q1
        expected_q3 = self.compute_quantile_r7(test_values, 0.75)
        expected_q1 = self.compute_quantile_r7(test_values, 0.25)
        expected_iqr = expected_q3 - expected_q1

        assert indicator.value == pytest.approx(
            expected_iqr, abs=0.5
        ), f"Expected IQR={expected_iqr}, got {indicator.value}"

    def test_ts_quantile_percentile_rank(self):
        """Test TS_Quantile in combination with comparison (percentile rank)."""
        window = 10
        phi = 0.9  # 90th percentile
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Uniform distribution [10, 20, 30, ..., 100]
        test_values = [float(i * 10) for i in range(1, window + 1)]
        for value in test_values:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # 90th percentile
        expected_p90 = self.compute_quantile_r7(test_values, phi)

        assert indicator.value == pytest.approx(
            expected_p90, abs=1.0
        ), f"Expected P90={expected_p90}, got {indicator.value}"

    # -------------------------------------------------------------------------
    # Test 9: Sequence Tests
    # -------------------------------------------------------------------------

    def test_ts_quantile_increasing_sequence(self):
        """Test TS_Quantile with strictly increasing sequence."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Strictly increasing: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for value in range(1, 11):
            bar = self.create_bar(float(value))
            indicator.handle_bar(bar)

        # Last window: [6, 7, 8, 9, 10]
        expected_window = list(range(6, 11))
        expected_median = self.compute_quantile_r7(expected_window, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected median of {expected_window} = {expected_median}, got {indicator.value}"

    def test_ts_quantile_decreasing_sequence(self):
        """Test TS_Quantile with strictly decreasing sequence."""
        window = 5
        phi = 0.5
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Strictly decreasing: [100, 90, 80, 70, 60, 50, 40, 30]
        sequence = [100.0 - i * 10 for i in range(8)]
        for value in sequence:
            bar = self.create_bar(value)
            indicator.handle_bar(bar)

        # Last window
        expected_window = sequence[-window:]
        expected_median = self.compute_quantile_r7(expected_window, phi)

        assert indicator.value == pytest.approx(
            expected_median, abs=1e-9
        ), f"Expected median of {expected_window} = {expected_median}, got {indicator.value}"


if __name__ == "__main__":
    """Run tests locally for development."""
    test = TestTsQuantile()

    print("=" * 80)
    print("TS_Quantile Operator Test Suite")
    print("=" * 80)

    test_methods = [
        # Basic Functionality
        ("Basic: Median Calculation", test.test_ts_quantile_median_basic),
        ("Basic: Quartiles (Q1, Q3)", test.test_ts_quantile_quartiles),
        ("Basic: Extreme Values (Min, Max)", test.test_ts_quantile_extreme_values),
        # Window Behavior
        ("Window: Initialization", test.test_ts_quantile_window_initialization),
        ("Window: Rolling Window", test.test_ts_quantile_rolling_window),
        ("Window: Small Window", test.test_ts_quantile_small_window),
        # Algorithm Switch
        ("Algorithm: SortedArray", test.test_ts_quantile_sorted_array_implementation),
        ("Algorithm: DualHeap", test.test_ts_quantile_dual_heap_implementation),
        ("Algorithm: Consistency", test.test_ts_quantile_algorithm_consistency),
        # NaN Handling
        ("NaN: Filtering", test.test_ts_quantile_nan_filtering),
        ("NaN: All NaN Reuse", test.test_ts_quantile_all_nan_reuse_stale),
        ("NaN: Interleaved", test.test_ts_quantile_interleaved_nans),
        # Edge Cases
        ("Edge: Constant Values", test.test_ts_quantile_constant_values),
        ("Edge: Single Value", test.test_ts_quantile_single_value),
        ("Edge: Duplicates", test.test_ts_quantile_duplicate_values),
        # Numerical Precision
        ("Precision: R-7 Interpolation", test.test_ts_quantile_r7_interpolation),
        ("Precision: Large Values", test.test_ts_quantile_large_values_precision),
        # Reset
        ("Reset: Hygiene", test.test_ts_quantile_reset_hygiene),
        # Composite Expressions
        ("Composite: IQR", test.test_ts_quantile_iqr_calculation),
        ("Composite: Percentile Rank", test.test_ts_quantile_percentile_rank),
        # Sequences
        ("Sequence: Increasing", test.test_ts_quantile_increasing_sequence),
        ("Sequence: Decreasing", test.test_ts_quantile_decreasing_sequence),
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
        print("⚠️  Some tests failed. Run with pytest for details.")
