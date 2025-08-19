
import math
import pytest
import time
import numpy as np
from typing import List, Dict, Tuple

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestFactorExpAdvanced:
    """Advanced test suite for FactorExp expressions."""
    
    def setup_method(self):
        """Set up test data and utilities."""
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
        # Create correlated test data for pair rolling operators
        self.correlated_data = [
            (100.0, 1000.0),  # close, volume
            (102.0, 1020.0),  # positive correlation
            (98.0, 980.0),
            (104.0, 1040.0),
            (96.0, 960.0),
            (106.0, 1060.0),
            (94.0, 940.0),
            (108.0, 1080.0),
            (92.0, 920.0),
            (110.0, 1100.0),
        ]
        
        # Create anti-correlated test data
        self.anti_correlated_data = [
            (100.0, 1000.0),  # close, volume
            (102.0, 980.0),   # negative correlation
            (98.0, 1020.0),
            (104.0, 960.0),
            (96.0, 1040.0),
            (106.0, 940.0),
            (94.0, 1060.0),
            (108.0, 920.0),
            (92.0, 1080.0),
            (110.0, 900.0),
        ]
        
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
    
    def feed_correlated_data(self, indicator: FactorExpIndicator, 
                           data: List[Tuple[float, float]], 
                           count: int = None):
        """Feed correlated test data to indicator."""
        if count is None:
            count = len(data)
        
        for i in range(min(count, len(data))):
            close, volume = data[i]
            # Create bars with correlated close/volume
            bar = self.create_bar(close, close + 1, close - 1, close, volume)
            indicator.handle_bar(bar)
    

    #TS_Mean($close, 10) / TS_Mean($close, 20)
    def test_sma_ratio_operator(self):
        """Test SMA Ratio operator."""
        indicator = FactorExpIndicator("TS_Mean($close, 10) / TS_Mean($close, 20)")
        
        # Feed data with known values
        known_values = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124, 126, 128, 130, 132, 134, 136, 138, 140]
        for value in known_values:
            bar = self.create_bar(value, value + 1, value - 1, value, 1000)
            indicator.handle_bar(bar)
            print(f"SMA Ratio value after feeding {value}: {indicator.value}")
    
    # ("($close - TS_Mean($close, 20)) / TS_Std($close, 20)", "Z-Score"),
    def test_z_score_operator(self):
        """Test Z-Score operator."""
        indicator = FactorExpIndicator("($close - TS_Mean($close, 20)) / TS_Std($close, 20)")
        
        # Feed data with known values
        known_values = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120,  
                        122, 124, 126, 128, 130, 132, 134, 136, 138, 140, 
                        142, 144, 146, 148, 150]
        for value in known_values:
            bar = self.create_bar(value, value + 1, value - 1, value, 1000)
            indicator.handle_bar(bar)
            print(f"Z-Score value after feeding {value}: {indicator.value}")

    # "TS_Mean(Abs($close - TS_Ref($close, 1)), 10)"
    def test_average_price_change(self):
        """Test Average Price Change operator."""
        indicator = FactorExpIndicator("TS_Mean(Abs($close - TS_Ref($close, 1)), 10)")
        
        # Feed data with known values
        known_values = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 
                        122, 124, 126, 128, 130, 132, 134, 136, 138, 140]
        for value in known_values:
            bar = self.create_bar(value, value + 1, value - 1, value, 1000)
            indicator.handle_bar(bar)
            print(f"Average Price Change after feeding {value}: {indicator.value}")


def run_advanced_test_suite():
    """Run the advanced test suite with detailed reporting."""
    test_instance = TestFactorExpAdvanced()
    test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
    
    print("=" * 80)
    print("Advanced FactorExp Test Suite")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        print(f"\nRunning {method_name}...")
        try:
            test_instance.setup_method()
            method = getattr(test_instance, method_name)
            method()
            print(f"✅ {method_name} - PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {method_name} - FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    # Run the advanced test suite
    success = run_advanced_test_suite()
    
    if success:
        print("🎉 All advanced tests passed!")
    else:
        print("⚠️  Some advanced tests failed - this may be expected for unimplemented features")