"""
Test cases for Clip operator in FactorExp.

Tests the Clip operator functionality through actual data processing,
ensuring values are correctly bounded within specified min/max ranges.
"""

import time

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


class TestClipOperator:
    """Test cases for the Clip operator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )

    def create_bar(self, close: float, high: float = None, low: float = None,
                   volume: float = 1000.0, open_price: float = None) -> Bar:
        """Create a test bar with specified values."""
        if open_price is None:
            open_price = close

        # If high/low not specified, calculate them
        if high is None:
            high = max(open_price, close) + 1.0
        if low is None:
            low = min(open_price, close) - 1.0

        # Ensure valid OHLC relationships
        assert high >= max(open_price, close), "High must be >= max(open, close)"
        assert low <= min(open_price, close), "Low must be <= min(open, close)"
        assert high >= low, "High must be >= low"

        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{open_price:.2f}"),
            high=Price.from_str(f"{high:.2f}"),
            low=Price.from_str(f"{low:.2f}"),
            close=Price.from_str(f"{close:.2f}"),
            volume=Quantity.from_str(f"{volume:.0f}"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )

    def test_clip_basic_functionality(self):
        """Test basic Clip operator with constant bounds."""
        # Clip($close, 50, 100) - clips close price to [50, 100] range
        indicator = FactorExpIndicator("Clip($close, 50, 100)")

        # Test 1: Value below min (30 < 50) - should clip to 50
        bar = self.create_bar(30.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 50.0) < 1e-6, f"Expected 50, got {indicator.value}"

        # Test 2: Value above max (120 > 100) - should clip to 100
        bar = self.create_bar(120.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

        # Test 3: Value within range (75) - should remain unchanged
        bar = self.create_bar(75.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 75.0) < 1e-6, f"Expected 75, got {indicator.value}"

    def test_clip_edge_cases(self):
        """Test Clip operator at exact boundary values."""
        # Clip($close, 50, 100)
        indicator = FactorExpIndicator("Clip($close, 50, 100)")

        # Test 1: Value exactly at min (50)
        bar = self.create_bar(50.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 50.0) < 1e-6, f"Expected 50, got {indicator.value}"

        # Test 2: Value exactly at max (100)
        bar = self.create_bar(100.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

    def test_clip_with_dynamic_bounds(self):
        """Test Clip operator with dynamic bounds from market data."""
        # Clip($close, $low, $high) - clips close to the bar's low/high range
        indicator = FactorExpIndicator("Clip($close, $low, $high)")

        # Test 1: Close within low/high range
        bar = self.create_bar(close=100.0, high=105.0, low=95.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

        # Test 2: Close somehow exceeds high (shouldn't happen in real data, but test the clipping)
        # We'll use an expression that could exceed: Clip($close * 1.1, $low, $high)
        indicator2 = FactorExpIndicator("Clip(Mul($close, 1.1), $low, $high)")
        bar = self.create_bar(close=100.0, high=105.0, low=95.0)  # close * 1.1 = 110 > high
        indicator2.handle_bar(bar)
        assert abs(indicator2.value - 105.0) < 1e-6, f"Expected 105 (high), got {indicator2.value}"

    def test_clip_with_expressions(self):
        """Test Clip operator with complex expressions."""
        # Clip($close * 1.2, 90, 110) - multiply close by 1.2 then clip
        indicator = FactorExpIndicator("Clip(Mul($close, 1.2), 90, 110)")

        # Test 1: Result within bounds (80 * 1.2 = 96)
        bar = self.create_bar(80.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 96.0) < 1e-6, f"Expected 96, got {indicator.value}"

        # Test 2: Result exceeds max (100 * 1.2 = 120 > 110)
        bar = self.create_bar(100.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 110.0) < 1e-6, f"Expected 110, got {indicator.value}"

        # Test 3: Result below min (70 * 1.2 = 84 < 90)
        bar = self.create_bar(70.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 90.0) < 1e-6, f"Expected 90, got {indicator.value}"

    def test_clip_with_normalized_range(self):
        """Test Clip for normalizing values to [0, 1] range."""
        # Normalize close position within daily range: Clip(($close - $low) / ($high - $low), 0, 1)
        # This calculates where close is within the day's range and ensures it's in [0, 1]
        indicator = FactorExpIndicator("Clip(Div(Sub($close, $low), Sub($high, $low)), 0, 1)")

        # Test 1: Close at midpoint of range
        bar = self.create_bar(close=100.0, high=110.0, low=90.0)
        # (100 - 90) / (110 - 90) = 10/20 = 0.5
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.5) < 1e-6, f"Expected 0.5, got {indicator.value}"

        # Test 2: Close at low
        bar = self.create_bar(close=90.0, high=110.0, low=90.0)
        # (90 - 90) / (110 - 90) = 0/20 = 0
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0, got {indicator.value}"

        # Test 3: Close at high
        bar = self.create_bar(close=110.0, high=110.0, low=90.0, open_price=105.0)
        # (110 - 90) / (110 - 90) = 20/20 = 1
        indicator.handle_bar(bar)
        assert abs(indicator.value - 1.0) < 1e-6, f"Expected 1, got {indicator.value}"

    def test_clip_with_conditional_logic(self):
        """Test Clip combined with conditional operators."""
        # Use Clip to bound a conditional result
        # When volume > 1000, return clipped close, else return 0
        # When($volume > 1000, Clip($close, 50, 100), 0)
        indicator = FactorExpIndicator("When(Greater($volume, 1000), Clip($close, 50, 100), 0)")

        # Test 1: Volume > 1000, close needs clipping (120 -> 100)
        bar = self.create_bar(close=120.0, volume=1500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

        # Test 2: Volume > 1000, close within bounds (75)
        bar = self.create_bar(close=75.0, volume=1500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 75.0) < 1e-6, f"Expected 75, got {indicator.value}"

        # Test 3: Volume <= 1000, should return 0 regardless of close
        bar = self.create_bar(close=75.0, volume=500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0, got {indicator.value}"

    def test_clip_with_moving_average(self):
        """Test Clip with moving averages to create bounded indicators."""
        # Clip a 3-period moving average to [95, 105] range
        indicator = FactorExpIndicator("Clip(TS_Mean($close, 3), 95, 105)")

        # Feed sequence of values
        values = [90.0, 100.0, 110.0]  # Average = 100
        for val in values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)

        # After 3 bars, mean should be 100, which is within [95, 105]
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

        # Add a high value that pushes average above 105
        bar = self.create_bar(120.0)  # New average: (100 + 110 + 120)/3 = 110
        indicator.handle_bar(bar)
        assert abs(indicator.value - 105.0) < 1e-6, f"Expected 105 (clipped), got {indicator.value}"

        # Add a low value that pulls average below 95
        values = [80.0, 85.0]
        for val in values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)
        # Last 3: 120, 80, 85 -> average = 95
        assert abs(indicator.value - 95.0) < 1e-6, f"Expected 95, got {indicator.value}"

    def test_clip_chain_operations(self):
        """Test multiple Clip operations chained together."""
        # First clip to wide range, then to narrow range
        # Clip(Clip($close, 40, 120), 60, 100)
        indicator = FactorExpIndicator("Clip(Clip($close, 40, 120), 60, 100)")

        # Test 1: Value below both ranges (30)
        # First clip: 30 -> 40, Second clip: 40 -> 60
        bar = self.create_bar(30.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 60.0) < 1e-6, f"Expected 60, got {indicator.value}"

        # Test 2: Value above both ranges (130)
        # First clip: 130 -> 120, Second clip: 120 -> 100
        bar = self.create_bar(130.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100, got {indicator.value}"

        # Test 3: Value between ranges (50)
        # First clip: 50 -> 50 (unchanged), Second clip: 50 -> 60
        bar = self.create_bar(50.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 60.0) < 1e-6, f"Expected 60, got {indicator.value}"

        # Test 4: Value in final range (80)
        # First clip: 80 -> 80, Second clip: 80 -> 80
        bar = self.create_bar(80.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 80.0) < 1e-6, f"Expected 80, got {indicator.value}"

    def test_clip_zero_range(self):
        """Test Clip with min equal to max (essentially converts to constant)."""
        # Clip($close, 100, 100) - forces all values to 100
        indicator = FactorExpIndicator("Clip($close, 100, 100)")

        # Test various input values - all should become 100
        test_values = [50.0, 100.0, 150.0, 99.9, 100.1]
        for val in test_values:
            bar = self.create_bar(val)
            indicator.handle_bar(bar)
            assert abs(indicator.value - 100.0) < 1e-6, f"Expected 100 for input {val}, got {indicator.value}"

    def test_clip_percentage_bounds(self):
        """Test Clip for percentage-based bounds."""
        # Clip returns to ±5% range: Clip(($close - $open) / $open, -0.05, 0.05)
        indicator = FactorExpIndicator("Clip(Div(Sub($close, $open), $open), -0.05, 0.05)")

        # Test 1: 10% gain (should be clipped to 5%)
        bar = self.create_bar(close=110.0, open_price=100.0)
        # (110 - 100) / 100 = 0.10 -> clipped to 0.05
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.05) < 1e-6, f"Expected 0.05, got {indicator.value}"

        # Test 2: 3% gain (within bounds)
        bar = self.create_bar(close=103.0, open_price=100.0)
        # (103 - 100) / 100 = 0.03
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.03) < 1e-6, f"Expected 0.03, got {indicator.value}"

        # Test 3: 8% loss (should be clipped to -5%)
        bar = self.create_bar(close=92.0, open_price=100.0)
        # (92 - 100) / 100 = -0.08 -> clipped to -0.05
        indicator.handle_bar(bar)
        assert abs(indicator.value - (-0.05)) < 1e-6, f"Expected -0.05, got {indicator.value}"


if __name__ == "__main__":
    test = TestClipOperator()
    test.setup_method()
    test.test_clip_basic_functionality()
    test.test_clip_edge_cases()
    test.test_clip_with_dynamic_bounds()
    test.test_clip_with_expressions()
    test.test_clip_with_normalized_range()
    test.test_clip_with_conditional_logic()
    test.test_clip_with_moving_average()
    test.test_clip_chain_operations()
    test.test_clip_zero_range()
    test.test_clip_percentage_bounds()
    print("All tests passed.")
