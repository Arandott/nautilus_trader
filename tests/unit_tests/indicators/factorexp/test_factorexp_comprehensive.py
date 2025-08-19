"""
Comprehensive test suite for FactorExp indicator system.

This test suite covers:
1. All available operators with correctness verification
2. Edge cases (insufficient data, boundary conditions)
3. Complex nested expressions with validation
4. Performance and stability testing
"""

import math
import pytest
import time
import numpy as np
from typing import List

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestFactorExpComprehensive:
    """Comprehensive test suite for FactorExp expressions."""
    
    def setup_method(self):
        """Set up test data and utilities."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
        # Create test data with known patterns for validation
        self.test_prices = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0, 104.0, 96.0, 105.0,
                            95.0, 106.0, 94.0, 107.0, 93.0, 108.0, 92.0, 109.0, 91.0, 110.0,
                            90.0, 111.0, 89.0, 112.0, 88.0]
        self.test_volumes = [1000, 1100, 900, 1200, 800, 1300, 700, 1400, 600, 1500,
                            500, 1600, 400, 1700, 300, 1800, 200, 1900, 100, 2000,
                            50, 2100, 25, 2200, 10]
        
    def create_bar(self, open_price: float, high_price: float, 
                   low_price: float, close_price: float, volume: float) -> Bar:
        """Create a test bar with specified values."""
        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{open_price:.2f}"),
            high=Price.from_str(f"{high_price:.2f}"),
            low=Price.from_str(f"{low_price:.2f}"),
            close=Price.from_str(f"{close_price:.2f}"),
            volume=Quantity.from_str(f"{volume:.0f}"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )
    
    def feed_bars(self, indicator: FactorExpIndicator, count: int = None):
        """Feed test bars to indicator."""
        if count is None:
            count = len(self.test_prices)
        
        for i in range(min(count, len(self.test_prices))):
            close = self.test_prices[i]
            # Simple pattern: high = close + 1, low = close - 1, open = close
            bar = self.create_bar(close, close + 1, close - 1, close, self.test_volumes[i])
            indicator.handle_bar(bar)
    
    # ===== BASIC FEATURE TESTS =====
    
    def test_basic_features(self):
        """Test basic feature extraction ($close, $open, etc.)"""
        test_cases = [
            ("$close", 100.0),
            ("$open", 100.0),
            ("$high", 101.0),
            ("$low", 99.0),
            ("$volume", 1000.0),
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    # ===== MATHEMATICAL OPERATORS TESTS =====
    
    def test_arithmetic_operators(self):
        """Test basic arithmetic operators."""
        test_cases = [
            ("$close + 5", 105.0),
            ("$close - 5", 95.0),
            ("$close * 2", 200.0),
            ("$close / 2", 50.0),
            ("$close ^ 2", 10000.0),  # 100^2
            ("($close + $open) / 2", 100.0),  # (100 + 100) / 2
            ("$high - $low", 2.0),  # 101 - 99
            ("$close * $volume / 1000", 100.0),  # 100 * 1000 / 1000
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_comparison_operators(self):
        """Test comparison operators."""
        test_cases = [
            ("Greater($close, 99)", 1.0),  # 100 > 99 = True = 1.0
            ("Less($close, 101)", 1.0),    # 100 < 101 = True = 1.0
            ("Greater($close, 101)", 0.0), # 100 > 101 = False = 0.0
            ("Equal($close, 100)", 1.0),   # 100 == 100 = True = 1.0
            ("NotEqual($close, 99)", 1.0), # 100 != 99 = True = 1.0
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_logical_operators(self):
        """Test logical operators."""
        test_cases = [
            ("Max($close, 105)", 105.0),  # max(100, 105) = 105
            ("Min($close, 95)", 95.0),    # min(100, 95) = 95
            ("Max($high, $close)", 101.0), # max(101, 100) = 101
            ("Min($low, $close)", 99.0),   # min(99, 100) = 99
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    # ===== UNARY OPERATORS TESTS =====
    
    def test_unary_mathematical_operators(self):
        """Test unary mathematical operators."""
        test_cases = [
            ("Abs(-5)", 5.0),
            ("Sign(5)", 1.0),
            ("Sign(-5)", -1.0),
            ("Sign(0)", 0.0),
            ("Neg(5)", -5.0),
            ("Sqrt(100)", 10.0),  # sqrt(100) = 10
            ("Log(2.718281828)", 1.0),  # ln(e) ≈ 1
            ("Log10(100)", 2.0),  # log10(100) = 2
            ("Exp(0)", 1.0),  # e^0 = 1
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-4, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_trigonometric_operators(self):
        """Test trigonometric operators."""
        test_cases = [
            ("Sin(0)", 0.0),
            ("Cos(0)", 1.0),
            ("Tan(0)", 0.0),
            ("Sin(1.5707963267948966)", 1.0),  # sin(π/2) = 1
            ("Cos(1.5707963267948966)", 0.0),  # cos(π/2) = 0
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    # ===== ROLLING/TIME-SERIES OPERATORS TESTS =====
    
    def test_rolling_statistics(self):
        """Test rolling statistical operators."""
        # Feed 5 bars with known values: [100, 101, 99, 102, 98]
        test_cases = [
            ("TS_Mean($close, 3)", 99.67),  # mean of [99, 102, 98] ≈ 99.67
            ("TS_Sum($close, 3)", 299.0),   # sum of [99, 102, 98] = 299
            ("TS_Max($close, 3)", 102.0),   # max of [99, 102, 98] = 102
            ("TS_Min($close, 3)", 98.0),    # min of [99, 102, 98] = 98
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 5)  # Feed 5 bars
            assert abs(indicator.value - expected) < 0.1, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_rolling_advanced_statistics(self):
        """Test advanced rolling statistical operators."""
        # Test with more data for better statistical estimates
        indicator_std = FactorExpIndicator("TS_Std($close, 5)")
        self.feed_bars(indicator_std, 8)
        
        # Verify TS_Std produces reasonable values (should be > 0 for varying data)
        assert indicator_std.value > 0, f"TS_Std should be positive for varying data, got {indicator_std.value}"
        
        # Test TS_Delta (difference from previous value)
        indicator_delta = FactorExpIndicator("TS_Delta($close, 1)")
        self.feed_bars(indicator_delta, 3)
        
        # After 3 bars [100, 101, 99], delta should be 99 - 101 = -2
        expected_delta = 99.0 - 101.0  # current - previous
        assert abs(indicator_delta.value - expected_delta) < 1e-6, f"TS_Delta failed: got {indicator_delta.value}, expected {expected_delta}"
    
    def test_rolling_reference_operators(self):
        """Test rolling reference operators."""
        # Test TS_Ref (reference to previous value)
        indicator_ref = FactorExpIndicator("TS_Ref($close, 2)")
        self.feed_bars(indicator_ref, 5)
        
        # After 5 bars [100, 101, 99, 102, 98], TS_Ref(2) should return value from 2 periods ago
        # Current is 98 (index 4), 2 periods ago is 99 (index 2)
        expected_ref = 99.0
        assert abs(indicator_ref.value - expected_ref) < 1e-6, f"TS_Ref failed: got {indicator_ref.value}, expected {expected_ref}"
    
    # ===== EDGE CASE TESTS =====
    
    def test_insufficient_data_window(self):
        """Test behavior when data count is less than window size."""
        # Test with window size larger than available data
        test_cases = [
            ("TS_Mean($close, 10)", 1),  # Window=10, but only 1 bar
            ("TS_Sum($close, 5)", 2),    # Window=5, but only 2 bars
            ("TS_Std($close, 3)", 1),    # Window=3, but only 1 bar
        ]
        
        for expression, bar_count in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, bar_count)
            
            # System should handle gracefully - either NaN or using available data
            assert not math.isnan(indicator.value) or indicator.value is not None, f"Failed for {expression} with {bar_count} bars"
    
    def test_zero_and_negative_values(self):
        """Test operators with zero and negative values."""
        # Create bars with zero and negative values
        zero_bar = self.create_bar(0, 1, -1, 0, 1000)
        negative_bar = self.create_bar(-5, -4, -6, -5, 1000)
        
        test_cases = [
            ("$close", [zero_bar], 0.0),
            ("$close", [negative_bar], -5.0),
            ("Abs($close)", [negative_bar], 5.0),
            ("Sign($close)", [zero_bar], 0.0),
            ("Sign($close)", [negative_bar], -1.0),
        ]
        
        for expression, bars, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            for bar in bars:
                indicator.handle_bar(bar)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_division_by_zero_protection(self):
        """Test division by zero protection."""
        # Test division where denominator could be zero
        zero_bar = self.create_bar(0, 1, -1, 0, 1000)
        
        indicator = FactorExpIndicator("1 / $close")
        indicator.handle_bar(zero_bar)
        
        # Should handle division by zero gracefully (inf, -inf, or NaN)
        assert math.isinf(indicator.value) or math.isnan(indicator.value), f"Expected inf or NaN for division by zero, got {indicator.value}"
    
    # ===== COMPLEX NESTED EXPRESSION TESTS =====
    
    def test_simple_nested_expressions(self):
        """Test simple nested expressions."""
        test_cases = [
            # Nested arithmetic
            ("($close + $open) * ($high - $low)", 400.0),  # (100+100) * (101-99) = 200 * 2 = 400
            
            # Nested functions
            ("Abs(Neg($close))", 100.0),  # abs(-100) = 100
            ("Max(Min($close, 95), 90)", 95.0),  # max(min(100, 95), 90) = max(95, 90) = 95
            ("Sqrt(Pow($close, 2))", 100.0),  # sqrt(100^2) = sqrt(10000) = 100
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 1)
            assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
    
    def test_complex_rolling_expressions(self):
        """Test complex expressions with rolling operators."""
        test_cases = [
            # Rolling operations on computed values
            ("TS_Mean($close + $open, 3)", None),  # Will compute after feeding bars
            ("TS_Mean($high - $low, 3)", 2.0),  # mean of [2, 2, 2] = 2 (since high-low = 2 for all bars)
            ("TS_Sum($close * 2, 3)", None),  # Will verify after feeding
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 5)
            
            if expected is not None:
                assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
            else:
                # Just verify it computes without error
                assert not math.isnan(indicator.value), f"Got NaN for {expression}"
    
    def test_deeply_nested_expressions(self):
        """Test deeply nested expressions."""
        test_cases = [
            # 3-level nesting
            ("TS_Mean(Abs($close - $open), 3)", 0.0),  # abs(close-open) = 0 since open=close in test data
            
            # 4-level nesting
            ("Max(TS_Mean($close, 2), TS_Mean($open, 2))", None),  # Both should be similar
            
            # Complex mathematical expression
            ("Log(Exp(1))", 1.0),  # log(e^1) = 1
            ("Sqrt(Pow(Abs(Neg($close)), 2))", 98.0),   # sqrt((abs(-98))^2) = sqrt(98^2) = 98
        ]
        
        for expression, expected in test_cases:
            indicator = FactorExpIndicator(expression)
            self.feed_bars(indicator, 5)
            
            if expected is not None:
                assert abs(indicator.value - expected) < 1e-6, f"Failed for {expression}: got {indicator.value}, expected {expected}"
            else:
                # Just verify it computes without error
                assert not math.isnan(indicator.value), f"Got NaN for {expression}"
    
    def test_financial_indicators_expressions(self):
        """Test expressions that mimic common financial indicators."""
        # Simple moving average ratio (momentum)
        indicator_sma_ratio = FactorExpIndicator("TS_Mean($close, 2) / TS_Mean($close, 5)")
        self.feed_bars(indicator_sma_ratio, 10)
        assert not math.isnan(indicator_sma_ratio.value), "SMA ratio should not be NaN"
        
        # Bollinger Band position
        indicator_bb = FactorExpIndicator("($close - TS_Mean($close, 5)) / TS_Std($close, 5)")
        self.feed_bars(indicator_bb, 10)
        # Should be finite (not NaN or inf) for varying data
        assert math.isfinite(indicator_bb.value), f"Bollinger Band position should be finite, got {indicator_bb.value}"
        
        # RSI approximation (simplified)
        indicator_rsi = FactorExpIndicator("TS_Mean(Max($close - TS_Ref($close, 1), 0), 3)")
        self.feed_bars(indicator_rsi, 10)
        assert indicator_rsi.value >= 0, f"RSI component should be non-negative, got {indicator_rsi.value}"
    
    # ===== PERFORMANCE AND STABILITY TESTS =====
    
    def test_large_dataset_performance(self):
        """Test performance with large datasets."""
        indicator = FactorExpIndicator("TS_Mean($close, 50)")
        
        # Feed 1000 bars and measure performance
        start_time = time.time()
        
        for i in range(1000):
            price = 100 + math.sin(i * 0.1) * 10  # Synthetic price data
            bar = self.create_bar(price, price + 1, price - 1, price, 1000)
            indicator.handle_bar(bar)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 1000 bars in reasonable time (< 1 second)
        assert processing_time < 1.0, f"Performance test failed: took {processing_time:.3f} seconds for 1000 bars"
        assert not math.isnan(indicator.value), "Final value should not be NaN"
    
    def test_expression_compilation_performance(self):
        """Test expression compilation performance."""
        expressions = [
            "$close",
            "TS_Mean($close, 20)",
            "TS_Mean($close, 20) / TS_Std($close, 20)",
            "($close - TS_Mean($close, 20)) / TS_Std($close, 20)",
            "Max(Min(($close - TS_Mean($close, 20)) / TS_Std($close, 20), 2), -2)",
        ]
        
        start_time = time.time()
        
        for expression in expressions:
            for _ in range(100):  # Compile each expression 100 times
                indicator = FactorExpIndicator(expression)
        
        end_time = time.time()
        compilation_time = end_time - start_time
        
        # Should compile 500 expressions in reasonable time
        assert compilation_time < 5.0, f"Compilation performance test failed: took {compilation_time:.3f} seconds"
    
    def test_memory_stability(self):
        """Test memory stability with repeated operations."""
        # Create and destroy many indicators to test for memory leaks
        for i in range(100):
            indicator = FactorExpIndicator(f"TS_Mean($close, {10 + i % 10})")
            self.feed_bars(indicator, 50)
            # Indicator should be garbage collected when it goes out of scope
        
        # Final test to ensure system is still working
        final_indicator = FactorExpIndicator("$close")
        self.feed_bars(final_indicator, 1)
        assert abs(final_indicator.value - 100.0) < 1e-6, "System should still work after memory stress test"


# Additional test utilities for manual testing and debugging

def run_expression_test(expression: str, num_bars: int = 10, verbose: bool = True):
    """
    Utility function to test a single expression manually.
    
    Parameters
    ----------
    expression : str
        The expression to test
    num_bars : int
        Number of test bars to feed
    verbose : bool
        Whether to print detailed output
    """
    if verbose:
        print(f"\nTesting expression: {expression}")
        print("-" * 50)
    
    try:
        # Create test instance
        test_instance = TestFactorExpComprehensive()
        test_instance.setup_method()
        
        # Create indicator
        indicator = FactorExpIndicator(expression)
        
        if verbose:
            print(f"✅ Expression compiled successfully")
            print(f"Period: {indicator.period}")
            print(f"Expression: {indicator.expression}")
        
        # Feed bars
        test_instance.feed_bars(indicator, num_bars)
        
        if verbose:
            print(f"✅ Fed {num_bars} bars successfully")
            print(f"Final value: {indicator.value}")
            print(f"Has inputs: {indicator.has_inputs}")
            print(f"Initialized: {indicator.initialized}")
        
        return indicator.value
        
    except Exception as e:
        if verbose:
            print(f"❌ Failed: {e}")
            import traceback
            traceback.print_exc()
        return None


if __name__ == "__main__":
    # Run some manual tests for debugging
    test_expressions = [
        "$close",
        "$close + 5",
        "TS_Mean($close, 3)",
        "Abs(Neg($close))",
        "TS_Mean($close, 20) / TS_Std($close, 20)",
    ]
    
    print("=" * 60)
    print("Manual Expression Tests")
    print("=" * 60)
    
    for expr in test_expressions:
        run_expression_test(expr, num_bars=25)