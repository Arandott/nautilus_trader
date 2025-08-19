#!/usr/bin/env python3
"""
Triple nested TS_Mean validation test with detailed step-by-step verification.
Tests: TS_Mean(TS_Mean(TS_Mean($close, 2), 2), 2)
"""

import sys
import math
from pathlib import Path
from typing import List, Optional

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.core.nautilus_pyo3 import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
import time


class TripleNestedMeanValidator:
    """Validator for triple nested TS_Mean expression with full calculation tracking."""
    
    def __init__(self):
        self.bar_type = BarType(
            instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
    def create_bar(self, close_price: float) -> Bar:
        """Create a test bar with specified close price."""
        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(f"{close_price:.2f}"),
            high=Price.from_str(f"{close_price + 0.5:.2f}"),
            low=Price.from_str(f"{close_price - 0.5:.2f}"),
            close=Price.from_str(f"{close_price:.2f}"),
            volume=Quantity.from_str("1000"),
            ts_event=int(time.time() * 1e9),
            ts_init=int(time.time() * 1e9),
        )
    
    def calculate_expected_values(self, close_prices: List[float]) -> dict:
        """Manually calculate expected values for each layer."""
        
        # Layer 1: TS_Mean($close, 2)
        layer1 = []
        for i in range(len(close_prices)):
            if i < 1:
                layer1.append(None)  # Not enough data
            else:
                # 2-period mean
                value = (close_prices[i-1] + close_prices[i]) / 2
                layer1.append(value)
        
        # Layer 2: TS_Mean(Layer1, 2)
        layer2 = []
        for i in range(len(layer1)):
            if i < 1 or layer1[i] is None or layer1[i-1] is None:
                layer2.append(None)
            else:
                value = (layer1[i-1] + layer1[i]) / 2
                layer2.append(value)
        
        # Layer 3: TS_Mean(Layer2, 2)
        layer3 = []
        for i in range(len(layer2)):
            if i < 1 or layer2[i] is None or layer2[i-1] is None:
                layer3.append(None)
            else:
                value = (layer2[i-1] + layer2[i]) / 2
                layer3.append(value)
        
        return {
            'layer1': layer1,
            'layer2': layer2,
            'layer3': layer3
        }
    
    def run_validation(self):
        """Run comprehensive validation of triple nested TS_Mean."""
        
        print("=" * 120)
        print(" " * 35 + "TRIPLE NESTED TS_MEAN VALIDATION")
        print(" " * 30 + "Expression: TS_Mean(TS_Mean(TS_Mean($close, 2), 2), 2)")
        print("=" * 120)
        
        # Generate test data: 20 bars with simple incremental prices
        close_prices = [100.0 + i * 0.5 for i in range(20)]
        
        # Calculate expected values manually
        expected = self.calculate_expected_values(close_prices)
        
        # Create indicators for each layer
        indicator_layer1 = FactorExpIndicator("TS_Mean($close, 2)")
        indicator_layer2 = FactorExpIndicator("TS_Mean(TS_Mean($close, 2), 2)")
        indicator_layer3 = FactorExpIndicator("TS_Mean(TS_Mean(TS_Mean($close, 2), 2), 2)")
        
        # Track actual values
        actual_layer1 = []
        actual_layer2 = []
        actual_layer3 = []
        
        # Feed bars and collect values
        for i, close_price in enumerate(close_prices):
            bar = self.create_bar(close_price)
            
            indicator_layer1.handle_bar(bar)
            indicator_layer2.handle_bar(bar)
            indicator_layer3.handle_bar(bar)
            
            val1 = None if math.isnan(indicator_layer1.value) else indicator_layer1.value
            val2 = None if math.isnan(indicator_layer2.value) else indicator_layer2.value
            val3 = None if math.isnan(indicator_layer3.value) else indicator_layer3.value
            
            actual_layer1.append(val1)
            actual_layer2.append(val2)
            actual_layer3.append(val3)
        
        # Print detailed validation table
        print("\n📊 DETAILED VALUE TRACKING (20 Bars)")
        print("-" * 120)
        
        # Table header
        header = "| Bar |  Close  | Layer1:Mean(2) | Expected L1 | ✓ | Layer2:Mean(2) | Expected L2 | ✓ | Layer3:Mean(2) | Expected L3 | ✓ |"
        separator = "|-----|---------|----------------|-------------|---|----------------|-------------|---|----------------|-------------|---|"
        print(header)
        print(separator)
        
        all_correct = True
        tolerance = 1e-6
        
        for i in range(20):
            # Check Layer 1
            l1_actual = actual_layer1[i]
            l1_expected = expected['layer1'][i]
            l1_match = self.check_match(l1_actual, l1_expected, tolerance)
            
            # Check Layer 2
            l2_actual = actual_layer2[i]
            l2_expected = expected['layer2'][i]
            l2_match = self.check_match(l2_actual, l2_expected, tolerance)
            
            # Check Layer 3
            l3_actual = actual_layer3[i]
            l3_expected = expected['layer3'][i]
            l3_match = self.check_match(l3_actual, l3_expected, tolerance)
            
            all_correct = all_correct and l1_match and l2_match and l3_match
            
            # Format values for display
            l1_actual_str = f"{l1_actual:8.3f}" if l1_actual is not None else "   NaN  "
            l1_expected_str = f"{l1_expected:8.3f}" if l1_expected is not None else "   NaN  "
            l2_actual_str = f"{l2_actual:8.3f}" if l2_actual is not None else "   NaN  "
            l2_expected_str = f"{l2_expected:8.3f}" if l2_expected is not None else "   NaN  "
            l3_actual_str = f"{l3_actual:8.3f}" if l3_actual is not None else "   NaN  "
            l3_expected_str = f"{l3_expected:8.3f}" if l3_expected is not None else "   NaN  "
            
            l1_check = "✅" if l1_match else "❌"
            l2_check = "✅" if l2_match else "❌"
            l3_check = "✅" if l3_match else "❌"
            
            print(f"| {i+1:3d} | {close_prices[i]:7.2f} | {l1_actual_str:14s} | {l1_expected_str:11s} | {l1_check} | "
                  f"{l2_actual_str:14s} | {l2_expected_str:11s} | {l2_check} | "
                  f"{l3_actual_str:14s} | {l3_expected_str:11s} | {l3_check} |")
        
        # Mathematical verification section
        print("\n📐 MATHEMATICAL VERIFICATION")
        print("-" * 120)
        
        # Show calculation details for a specific bar (e.g., bar 5)
        example_bar = 4  # 0-indexed
        print(f"\nDetailed Calculation for Bar {example_bar + 1}:")
        print(f"Close prices: {close_prices[:example_bar+1]}")
        
        if expected['layer1'][example_bar] is not None:
            print(f"\nLayer 1: TS_Mean($close, 2)")
            print(f"  = ({close_prices[example_bar-1]:.2f} + {close_prices[example_bar]:.2f}) / 2")
            print(f"  = {expected['layer1'][example_bar]:.3f}")
        
        if expected['layer2'][example_bar] is not None:
            print(f"\nLayer 2: TS_Mean(Layer1, 2)")
            print(f"  Layer1 values: {[f'{v:.3f}' if v else 'NaN' for v in expected['layer1'][:example_bar+1]]}")
            print(f"  = ({expected['layer1'][example_bar-1]:.3f} + {expected['layer1'][example_bar]:.3f}) / 2")
            print(f"  = {expected['layer2'][example_bar]:.3f}")
        
        if expected['layer3'][example_bar] is not None:
            print(f"\nLayer 3: TS_Mean(Layer2, 2)")
            print(f"  Layer2 values: {[f'{v:.3f}' if v else 'NaN' for v in expected['layer2'][:example_bar+1]]}")
            print(f"  = ({expected['layer2'][example_bar-1]:.3f} + {expected['layer2'][example_bar]:.3f}) / 2")
            print(f"  = {expected['layer3'][example_bar]:.3f}")
        
        # Summary statistics
        print("\n📊 VALIDATION STATISTICS")
        print("-" * 120)
        
        # Count valid values per layer
        valid_l1 = sum(1 for v in actual_layer1 if v is not None)
        valid_l2 = sum(1 for v in actual_layer2 if v is not None)
        valid_l3 = sum(1 for v in actual_layer3 if v is not None)
        
        print(f"Layer 1 (TS_Mean($close, 2)):           {valid_l1}/20 valid values")
        print(f"Layer 2 (TS_Mean(Layer1, 2)):           {valid_l2}/20 valid values")
        print(f"Layer 3 (TS_Mean(Layer2, 2)):           {valid_l3}/20 valid values")
        
        # Check all matches
        l1_matches = sum(1 for i in range(20) if self.check_match(actual_layer1[i], expected['layer1'][i], tolerance))
        l2_matches = sum(1 for i in range(20) if self.check_match(actual_layer2[i], expected['layer2'][i], tolerance))
        l3_matches = sum(1 for i in range(20) if self.check_match(actual_layer3[i], expected['layer3'][i], tolerance))
        
        print(f"\nCorrectness:")
        print(f"Layer 1: {l1_matches}/20 correct values")
        print(f"Layer 2: {l2_matches}/20 correct values")
        print(f"Layer 3: {l3_matches}/20 correct values")
        
        # Final result
        print("\n" + "=" * 120)
        if all_correct:
            print("🎉 " + " " * 30 + "ALL VALUES CORRECT - TRIPLE NESTING VALIDATED!" + " " * 30 + " 🎉")
            print(" " * 25 + "Architecture handles arbitrary nesting depth perfectly!")
        else:
            print("❌ " + " " * 30 + "VALIDATION FAILED - SOME VALUES INCORRECT" + " " * 30 + " ❌")
            print(" " * 30 + "Please check the implementation for issues")
        print("=" * 120)
        
        return all_correct
    
    def check_match(self, actual: Optional[float], expected: Optional[float], tolerance: float) -> bool:
        """Check if actual and expected values match within tolerance."""
        if actual is None and expected is None:
            return True
        if actual is None or expected is None:
            return False
        return abs(actual - expected) < tolerance


def main():
    """Main test execution."""
    validator = TripleNestedMeanValidator()
    success = validator.run_validation()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())