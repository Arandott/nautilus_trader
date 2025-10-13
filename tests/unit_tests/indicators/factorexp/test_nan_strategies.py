"""
Python-Side NaN Handling Test Suite for FactorExp.

Validates refactored NaN semantics from Python bindings to ensure end-to-end
behaviour mirrors Rust operators. Focuses on rolling statistics with comprehensive
NaN handling scenarios.

Test Matrix:
1. Readiness vs. NaN Density
2. Std NaN Reuse & Staleness
3. Std with Alternating NaNs
4. Std Edge Conditions
5. Pair Operator Alignment (Correlation)
6. Quantile Reset Hygiene
7. Skew/Kurt Valid-Length Gates
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


# -----------------------------------------------------------------------------
# Test Fixtures & Helper Functions
# -----------------------------------------------------------------------------


class TestNaNStrategies:
    """Comprehensive NaN handling test suite for FactorExp operators."""

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

    def compute_nanstd_manual(self, values: list[float], ddof: int = 1) -> float:
        """
        Compute standard deviation filtering out NaN values manually.

        Args:
            values: List of values (may contain NaN)
            ddof: Degrees of freedom (default 1 for sample std)

        Returns:
            Standard deviation of valid values, or NaN if insufficient data
        """
        valid = [v for v in values if not math.isnan(v)]
        if len(valid) <= ddof:
            return float("nan")
        return statistics.stdev(valid) if len(valid) > 1 else 0.0

    # -------------------------------------------------------------------------
    # Test 1: Readiness vs. NaN Density
    # -------------------------------------------------------------------------

    def test_readiness_leading_nans(self):
        """Test readiness with leading NaNs."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Mean($close, {window})")

        # Feed: [NaN, NaN, 1.0, 2.0, 3.0]
        values = [float("nan"), float("nan"), 1.0, 2.0, 3.0]
        snapshots = self.feed_series(indicator, values)

        # After window_size updates, should be ready regardless of NaN density
        assert indicator.initialized, "Indicator should be initialized after window_size updates"
        assert not math.isnan(
            indicator.value
        ), "Should have valid value with some valid data"

    def test_readiness_trailing_nans(self):
        """Test readiness with trailing NaNs."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Feed: [1.0, 2.0, 3.0, NaN, NaN]
        values = [1.0, 2.0, 3.0, float("nan"), float("nan")]
        self.feed_series(indicator, values)

        assert indicator.initialized, "Should be initialized after window_size updates"
        # Value should be stale (last valid std from [1, 2, 3])
        assert not math.isnan(indicator.value), "Should reuse last valid value"

    def test_readiness_interleaved_nans(self):
        """Test readiness with interleaved NaNs."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Sum($close, {window})")

        # Feed: [1.0, NaN, 2.0, NaN, 3.0]
        values = [1.0, float("nan"), 2.0, float("nan"), 3.0]
        self.feed_series(indicator, values)

        assert indicator.initialized, "Should be initialized despite interleaved NaNs"
        # Sum of valid values: 1 + 2 + 3 = 6
        assert indicator.value == pytest.approx(6.0, abs=1e-9)

    # -------------------------------------------------------------------------
    # Test 2: Std NaN Reuse & Staleness
    # -------------------------------------------------------------------------

    def test_std_nan_reuse_staleness(self):
        """Test Std reuses last valid value when window degenerates to all NaN."""
        window = 3
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Phase 1: Feed valid values [1, 2, 3]
        values_valid = [1.0, 2.0, 3.0]
        self.feed_series(indicator, values_valid)

        assert indicator.initialized
        last_valid_std = indicator.value
        expected_std = statistics.stdev(values_valid)
        assert last_valid_std == pytest.approx(expected_std, rel=1e-9)

        # Phase 2: Degenerate to all NaN
        nan_values = [float("nan"), float("nan")]
        self.feed_series(indicator, nan_values)

        # Should reuse last valid std (not emit NaN or zero)
        assert indicator.value == pytest.approx(
            last_valid_std, rel=1e-9
        ), "Should reuse last valid std"
        assert not math.isnan(indicator.value), "Should not return NaN"

    # -------------------------------------------------------------------------
    # Test 3: Std with Alternating NaNs
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "values,expected_positions",
        [
            (
                [1.0, float("nan"), 2.0, float("nan"), 3.0, float("nan"), 4.0],
                [
                    (2, [1.0, 2.0]),  # Position 2: window [1, NaN, 2] → valid [1, 2]
                    (4, [2.0, 3.0]),  # Position 4: window [2, NaN, 3] → valid [2, 3]
                    (6, [3.0, 4.0]),  # Position 6: window [3, NaN, 4] → valid [3, 4]
                ],
            ),
        ],
    )
    def test_std_alternating_nans(self, values, expected_positions):
        """Test Std with alternating valid/NaN inputs over sequences."""
        window = 3
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        snapshots = self.feed_series(indicator, values)

        for pos, expected_valid in expected_positions:
            actual_std = snapshots[pos][0]
            expected_std = self.compute_nanstd_manual(expected_valid, ddof=1)

            assert actual_std == pytest.approx(
                expected_std, rel=1e-6, abs=1e-9
            ), f"Position {pos}: expected std of {expected_valid} = {expected_std}, got {actual_std}"

    # -------------------------------------------------------------------------
    # Test 4: Std Edge Conditions
    # -------------------------------------------------------------------------

    def test_std_edge_insufficient_valid_values(self):
        """Test Std with valid count <= ddof (should reuse stale value)."""
        window = 4
        indicator = FactorExpIndicator(f"TS_Std($close, {window})")

        # Phase 1: Establish valid baseline [1, 2, 3, 4]
        baseline = [1.0, 2.0, 3.0, 4.0]
        self.feed_series(indicator, baseline)
        assert indicator.initialized
        last_valid = indicator.value

        # Phase 2: Feed data with only 1 valid sample (< ddof=1 + 1)
        # Window becomes [NaN, 1, NaN, NaN] → only 1 valid value
        edge_values = [float("nan"), 1.0, float("nan"), float("nan")]
        self.feed_series(indicator, edge_values)

        # Should reuse last valid std (insufficient data for new computation)
        assert indicator.value == pytest.approx(
            last_valid, rel=1e-9
        ), "Should reuse stale value with insufficient valid samples"

    # -------------------------------------------------------------------------
    # Test 5: Pair Operator Alignment (Correlation)
    # -------------------------------------------------------------------------

    def test_correlation_mismatched_nans(self):
        """Test Correlation with mismatched NaNs between X and Y."""
        window = 4
        # Correlation requires two inputs; we'll use $close as X and $open as Y
        indicator = FactorExpIndicator(f"Corr($close, $open, {window})")

        # Create bars with mismatched NaNs:
        # (close, open): (1,1), (NaN,2), (3,NaN), (4,4)
        test_bars = [
            (1.0, 1.0),  # Both valid
            (float("nan"), 2.0),  # close=NaN, open=valid
            (3.0, float("nan")),  # close=valid, open=NaN
            (4.0, 4.0),  # Both valid
        ]

        for close_val, open_val in test_bars:
            bar = self.create_bar(close=close_val, open_price=open_val)
            indicator.handle_bar(bar)

        # After 4 updates, should be initialized
        assert indicator.initialized

        # Only jointly valid pairs: (1,1) and (4,4)
        # Correlation of [(1,1), (4,4)] → perfect positive correlation = 1.0
        # Note: With only 2 points, correlation is always ±1.0 or undefined
        # For this test, we verify it's a valid finite value
        assert not math.isnan(
            indicator.value
        ), "Correlation should be valid with jointly-valid pairs"
        assert math.isfinite(indicator.value), "Correlation should be finite"

    # -------------------------------------------------------------------------
    # Test 6: Quantile Reset Hygiene
    # -------------------------------------------------------------------------

    def test_quantile_reset_hygiene(self):
        """Test Quantile reset does not leak previous statistics."""
        window = 5
        phi = 0.5  # Median
        indicator = FactorExpIndicator(f"TS_Quantile($close, {window}, {phi})")

        # Phase 1: Warm operator with initial data [100, 101, 102, 103, 104]
        initial_data = [100.0, 101.0, 102.0, 103.0, 104.0]
        self.feed_series(indicator, initial_data)
        assert indicator.initialized
        initial_median = indicator.value
        assert initial_median == pytest.approx(102.0, abs=1e-9)

        # Reset operator
        indicator.reset()
        assert not indicator.initialized, "Should not be initialized after reset"

        # Phase 2: Feed new data with NaNs [1, NaN, 2, 3, 4]
        new_data = [1.0, float("nan"), 2.0, 3.0, 4.0]
        self.feed_series(indicator, new_data)

        assert indicator.initialized
        # Median of valid values [1, 2, 3, 4] = 2.5
        expected_new_median = statistics.median([1.0, 2.0, 3.0, 4.0])
        assert indicator.value == pytest.approx(
            expected_new_median, abs=1e-6
        ), "New median should not be influenced by pre-reset data"
        assert abs(indicator.value - initial_median) > 50.0, "Medians should be significantly different"

    # -------------------------------------------------------------------------
    # Test 7: Skew/Kurt Valid-Length Gates
    # -------------------------------------------------------------------------

    def test_skew_insufficient_valid_samples(self):
        """Test Skew with insufficient valid samples (<3)."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Skew($close, {window})")

        # Phase 1: Establish baseline with valid data [1, 2, 3, 4, 5]
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.feed_series(indicator, baseline)
        assert indicator.initialized
        last_valid_skew = indicator.value

        # Phase 2: Feed data with only 2 valid samples
        # Window: [NaN, 1, NaN, NaN, 2] → only 2 valid values
        sparse_data = [float("nan"), 1.0, float("nan"), float("nan"), 2.0]
        self.feed_series(indicator, sparse_data)

        # Should reuse last valid skew (< 3 valid samples)
        assert indicator.value == pytest.approx(
            last_valid_skew, rel=1e-9
        ), "Should reuse stale skew with <3 valid samples"

    def test_skew_sufficient_valid_samples_after_sparse(self):
        """Test Skew resumes computation once sufficient valid samples arrive."""
        window = 5
        indicator = FactorExpIndicator(f"TS_Skew($close, {window})")

        # Phase 1: Sparse valid data (insufficient)
        sparse_data = [1.0, float("nan"), float("nan"), float("nan"), 2.0]
        self.feed_series(indicator, sparse_data)

        # Phase 2: Add more valid samples
        # Window becomes: [NaN, NaN, 2, 3, 4] → 3 valid samples
        new_data = [3.0, 4.0]
        self.feed_series(indicator, new_data)

        # Now should compute skew from [2, 3, 4]
        assert not math.isnan(indicator.value), "Should compute skew with >=3 valid samples"

    def test_kurtosis_insufficient_valid_samples(self):
        """Test Kurtosis with insufficient valid samples (<4)."""
        window = 6
        indicator = FactorExpIndicator(f"TS_Kurt($close, {window})")

        # Phase 1: Establish baseline [1, 2, 3, 4, 5, 6]
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        self.feed_series(indicator, baseline)
        assert indicator.initialized
        last_valid_kurt = indicator.value

        # Phase 2: Feed data with only 3 valid samples
        # Window: [NaN, 1, NaN, 2, NaN, 3] → only 3 valid values
        sparse_data = [float("nan"), 1.0, float("nan"), 2.0, float("nan"), 3.0]
        self.feed_series(indicator, sparse_data)

        # Should reuse last valid kurtosis (< 4 valid samples)
        assert indicator.value == pytest.approx(
            last_valid_kurt, rel=1e-9
        ), "Should reuse stale kurtosis with <4 valid samples"

    def test_kurtosis_zero_variance(self):
        """Test Kurtosis with zero variance (all same values)."""
        window = 6
        indicator = FactorExpIndicator(f"TS_Kurt($close, {window})")

        # Feed constant values
        constant_data = [10.0] * 6
        self.feed_series(indicator, constant_data)

        # Zero variance case should return NaN or reuse stale
        # Based on implementation, zero variance triggers stale value reuse
        # Since there's no prior valid value, should be NaN
        assert math.isnan(indicator.value), "Zero variance should result in NaN"


# -----------------------------------------------------------------------------
# Standalone Execution for Development
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    """Run tests locally for development."""
    test = TestNaNStrategies()

    print("=" * 80)
    print("NaN Strategies Test Suite for FactorExp")
    print("=" * 80)

    test_methods = [
        # Test 1: Readiness
        ("Readiness: Leading NaNs", test.test_readiness_leading_nans),
        ("Readiness: Trailing NaNs", test.test_readiness_trailing_nans),
        ("Readiness: Interleaved NaNs", test.test_readiness_interleaved_nans),
        # Test 2: Std Staleness
        ("Std: NaN Reuse & Staleness", test.test_std_nan_reuse_staleness),
        # Test 3: Alternating NaNs (skip parametrized in standalone)
        # Test 4: Edge Conditions
        ("Std: Edge Insufficient Valid", test.test_std_edge_insufficient_valid_values),
        # Test 5: Correlation
        ("Correlation: Mismatched NaNs", test.test_correlation_mismatched_nans),
        # Test 6: Quantile Reset
        ("Quantile: Reset Hygiene", test.test_quantile_reset_hygiene),
        # Test 7: Skew/Kurt Gates
        ("Skew: Insufficient Valid Samples", test.test_skew_insufficient_valid_samples),
        ("Skew: Sufficient After Sparse", test.test_skew_sufficient_valid_samples_after_sparse),
        ("Kurtosis: Insufficient Valid Samples", test.test_kurtosis_insufficient_valid_samples),
        ("Kurtosis: Zero Variance", test.test_kurtosis_zero_variance),
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
