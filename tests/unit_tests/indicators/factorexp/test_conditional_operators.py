"""
Test cases for conditional operators in FactorExp.

Tests the When, And, and Or operators functionality through actual data processing.
"""

import time
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestConditionalOperators:
    """Test cases for conditional operators."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )

    def create_bar(self, close: float, volume: float = 1000.0, open_price: float = None) -> Bar:
        """Create a test bar with specified values."""
        if open_price is None:
            open_price = close

        # Ensure valid OHLC relationships:
        # high >= max(open, close) and low <= min(open, close)
        base_price = min(open_price, close)
        max_price = max(open_price, close)

        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{open_price:.2f}"),
            high=Price.from_str(f"{max_price + 1:.2f}"),  # high must be >= both open and close
            low=Price.from_str(f"{base_price - 1:.2f}"),   # low must be <= both open and close
            close=Price.from_str(f"{close:.2f}"),
            volume=Quantity.from_str(f"{volume:.0f}"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )

    def test_when_operator_functionality(self):
        """Test that When operator works correctly with real data."""
        # When($close > 100, $close, 0) - returns close when > 100, else 0
        indicator = FactorExpIndicator("When(Greater($close, 100), $close, 0)")

        # Test with close = 105 (condition true)
        bar = self.create_bar(105.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 105.0) < 1e-6, f"Expected 105, got {indicator.value}"

        # Test with close = 95 (condition false)
        bar = self.create_bar(95.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0, got {indicator.value}"

    def test_and_operator_functionality(self):
        """Test that And operator works correctly."""
        # And($close > 100, $volume > 1000) - true when both conditions met
        indicator = FactorExpIndicator("And(Greater($close, 100), Greater($volume, 1000))")

        # Test with close = 105, volume = 1500 (both true)
        bar = self.create_bar(105.0, 1500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 1.0) < 1e-6, f"Expected 1 (true), got {indicator.value}"

        # Test with close = 105, volume = 500 (first true, second false)
        bar = self.create_bar(105.0, 500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0 (false), got {indicator.value}"

        # Test with close = 95, volume = 1500 (first false, second true)
        bar = self.create_bar(95.0, 1500.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0 (false), got {indicator.value}"

    def test_or_operator_functionality(self):
        """Test that Or operator works correctly."""
        # Or($close > 100, $volume > 1500) - true when either condition met
        indicator = FactorExpIndicator("Or(Greater($close, 100), Greater($volume, 1500))")

        # Test with close = 105, volume = 1000 (first true, second false)
        bar = self.create_bar(105.0, 1000.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 1.0) < 1e-6, f"Expected 1 (true), got {indicator.value}"

        # Test with close = 95, volume = 2000 (first false, second true)
        bar = self.create_bar(95.0, 2000.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 1.0) < 1e-6, f"Expected 1 (true), got {indicator.value}"

        # Test with close = 95, volume = 1000 (both false)
        bar = self.create_bar(95.0, 1000.0)
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0 (false), got {indicator.value}"

    def test_complex_conditional_expression(self):
        """Test a complex expression with multiple conditional operators."""
        # When volume is high AND price is rising, return close*1.1, otherwise close*0.9
        expr = "When(And(Greater($volume, 10000), Greater($close, $open)), $close * 1.1, $close * 0.9)"
        indicator = FactorExpIndicator(expr)

        # Test with high volume and rising price (condition true)
        bar = self.create_bar(105.0, 15000.0, open_price=100.0)
        indicator.handle_bar(bar)
        expected = 105.0 * 1.1
        assert abs(indicator.value - expected) < 1e-4, f"Expected {expected}, got {indicator.value}"

        # Test with low volume (condition false)
        bar = self.create_bar(105.0, 5000.0, open_price=100.0)
        indicator.handle_bar(bar)
        expected = 105.0 * 0.9
        assert abs(indicator.value - expected) < 1e-4, f"Expected {expected}, got {indicator.value}"

    def test_nested_when_operators(self):
        """Test nested When operators for multi-condition logic."""
        # Nested When: different values based on multiple conditions
        # When volume > 10000: When close > 100: return close*2, else close
        # else: return 0
        expr = "When(Greater($volume, 10000), When(Greater($close, 100), $close * 2, $close), 0)"
        indicator = FactorExpIndicator(expr)

        # Test with high volume and high close
        bar = self.create_bar(105.0, 15000.0)
        indicator.handle_bar(bar)
        expected = 105.0 * 2
        assert abs(indicator.value - expected) < 1e-4, f"Expected {expected}, got {indicator.value}"

        # Test with high volume but low close
        bar = self.create_bar(95.0, 15000.0)
        indicator.handle_bar(bar)
        expected = 95.0
        assert abs(indicator.value - expected) < 1e-4, f"Expected {expected}, got {indicator.value}"

        # Test with low volume (outer condition false)
        bar = self.create_bar(105.0, 5000.0)
        indicator.handle_bar(bar)
        expected = 0.0
        assert abs(indicator.value - expected) < 1e-6, f"Expected {expected}, got {indicator.value}"

    def test_when_with_rolling_operators(self):
        """Test When operator with rolling operators."""
        # When 3-bar moving average > current close, signal 1, else 0
        indicator = FactorExpIndicator("When(Greater(TS_Mean($close, 3), $close), 1, 0)")

        # Feed some bars to build up the moving average
        bars = [
            self.create_bar(100.0),
            self.create_bar(102.0),
            self.create_bar(104.0),  # MA = 102
            self.create_bar(98.0),   # MA = 101.33, close = 98, condition true
        ]

        for i, bar in enumerate(bars):
            indicator.handle_bar(bar)

        # After 4th bar: MA(102, 104, 98) = 101.33 > 98
        assert abs(indicator.value - 1.0) < 1e-6, f"Expected 1, got {indicator.value}"

        # Add a high close bar
        bar = self.create_bar(110.0)  # MA = 104, close = 110, condition false
        indicator.handle_bar(bar)
        assert abs(indicator.value - 0.0) < 1e-6, f"Expected 0, got {indicator.value}"


# Example usage demonstrations
def example_conditional_expressions():
    """
    Example expressions using conditional operators.

    These examples show how to use When, And, and Or operators
    in FactorExp expressions for creating trading signals.
    """

    # Example 1: Volume filter - only calculate when volume is significant
    volume_filter = "When(Greater($volume, 10000), $close, 0)"

    # Example 2: Bullish signal - price above MA AND volume increasing
    bullish_signal = "And(Greater($close, TS_Mean($close, 20)), Greater($volume, TS_Mean($volume, 10)))"

    # Example 3: Entry condition - either breakout OR reversal
    entry_condition = "Or(Greater($close, TS_Max($high, 20)), Less($close, TS_Min($low, 20) * 0.98))"

    # Example 4: Conditional indicator - different calculations based on market condition
    conditional_indicator = "When(Greater($volume, TS_Mean($volume, 20)), $close / TS_Mean($close, 10), $close / TS_Mean($close, 50))"

    # Example 5: Multi-condition filter using nested logic
    complex_filter = "When(And(Greater($close, 50), Or(Greater($volume, 100000), Greater(TS_Std($close, 20), 2))), $close * 1.01, 0)"

    return {
        "volume_filter": volume_filter,
        "bullish_signal": bullish_signal,
        "entry_condition": entry_condition,
        "conditional_indicator": conditional_indicator,
        "complex_filter": complex_filter,
    }


if __name__ == "__main__":
    # Run basic tests
    test = TestConditionalOperators()
    test.setup_method()

    print("Testing When operator functionality...")
    test.test_when_operator_functionality()
    print("✓ When operator functionality successful")

    print("Testing And operator functionality...")
    test.test_and_operator_functionality()
    print("✓ And operator functionality successful")

    print("Testing Or operator functionality...")
    test.test_or_operator_functionality()
    print("✓ Or operator functionality successful")

    print("Testing complex conditional expressions...")
    test.test_complex_conditional_expression()
    print("✓ Complex conditional expressions successful")

    print("Testing nested When operators...")
    test.test_nested_when_operators()
    print("✓ Nested When operators successful")

    print("Testing When with rolling operators...")
    test.test_when_with_rolling_operators()
    print("✓ When with rolling operators successful")

    print("\nExample conditional expressions:")
    examples = example_conditional_expressions()
    for name, expr in examples.items():
        print(f"\n{name}:\n{expr}")

    print("\n✓ All conditional operator tests passed!")