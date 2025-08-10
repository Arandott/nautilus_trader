# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""Integration tests for FactorExp indicator."""

import pytest
import numpy as np
from decimal import Decimal

from nautilus_trader.indicators.factorexp import FactorExpIndicator, SecurityConfig
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import AggressorSide, BarAggregation, PriceType, AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestFactorExpIntegration:
    """Integration tests for the complete FactorExp system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test instrument and bar type
        self.instrument_id = InstrumentId(Symbol("TEST"), Venue("VENUE"))
        self.bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE),
            aggregation_source=AggregationSource.EXTERNAL,
        )
    
    def create_test_bar(self, close: float, volume: float = 1000.0, timestamp: int = 0) -> Bar:
        """Create a test bar with specified values."""
        return Bar(
            bar_type=self.bar_type,
            open=Price.from_str(str(close)),
            high=Price.from_str(str(close * 1.01)),
            low=Price.from_str(str(close * 0.99)),
            close=Price.from_str(str(close)),
            volume=Quantity.from_str(str(volume)),
            ts_event=timestamp,
            ts_init=timestamp,
        )
    
    def test_simple_feature(self):
        """Test simple feature extraction."""
        indicator = FactorExpIndicator("$close")
        
        # Process a bar
        bar = self.create_test_bar(100.0)
        indicator.handle_bar(bar)
        
        assert indicator.has_inputs
        assert indicator.initialized
        assert indicator.value == 100.0
    
    def test_arithmetic_operations(self):
        """Test basic arithmetic operations."""
        # Addition
        indicator = FactorExpIndicator("$close + 10")
        indicator.handle_bar(self.create_test_bar(100.0))
        assert indicator.value == 110.0
        
        # Multiplication
        indicator = FactorExpIndicator("$close * 2")
        indicator.handle_bar(self.create_test_bar(50.0))
        assert indicator.value == 100.0
        
        # Division
        indicator = FactorExpIndicator("$high / $low")
        indicator.handle_bar(self.create_test_bar(100.0))
        assert abs(indicator.value - 1.0202) < 0.0001  # (101 / 99)
    
    def test_unary_operations(self):
        """Test unary operations."""
        # Absolute value
        indicator = FactorExpIndicator("Abs($close - 110)")
        indicator.handle_bar(self.create_test_bar(100.0))
        assert indicator.value == 10.0
        
        # Sign
        indicator = FactorExpIndicator("Sign($close - 100)")
        indicator.handle_bar(self.create_test_bar(105.0))
        assert indicator.value == 1.0
        
        # Log
        indicator = FactorExpIndicator("Log($close)")
        indicator.handle_bar(self.create_test_bar(np.e))
        assert abs(indicator.value - 1.0) < 0.0001
    
    def test_rolling_mean(self):
        """Test rolling mean calculation."""
        indicator = FactorExpIndicator("TS_Mean($close, 3)", period=3)
        
        # Feed data
        prices = [100.0, 102.0, 104.0, 106.0]
        for i, price in enumerate(prices):
            indicator.handle_bar(self.create_test_bar(price, timestamp=i))
        
        # After 3 bars, should have mean of last 3
        assert indicator.initialized
        assert indicator.value == pytest.approx(104.0)  # Mean of [102, 104, 106]
    
    def test_rolling_std(self):
        """Test rolling standard deviation."""
        indicator = FactorExpIndicator("TS_Std($close, 3)", period=3)
        
        # Feed data with some variance
        prices = [100.0, 105.0, 95.0, 100.0]
        for i, price in enumerate(prices):
            indicator.handle_bar(self.create_test_bar(price, timestamp=i))
        
        # Should have std of last 3 values [105, 95, 100]
        assert indicator.initialized
        assert indicator.value > 0  # Should have some standard deviation
    
    def test_complex_expression(self):
        """Test complex nested expression."""
        # Sharpe-like ratio
        expr = "TS_Mean($close, 5) / TS_Std($close, 5)"
        indicator = FactorExpIndicator(expr, period=5)
        
        # Feed data
        prices = [100, 101, 99, 102, 98, 103, 97]
        for i, price in enumerate(prices):
            indicator.handle_bar(self.create_test_bar(float(price), timestamp=i))
        
        # After 5 bars, should have a ratio
        if indicator.initialized:
            assert indicator.value != 0.0
    
    def test_vwap_calculation(self):
        """Test volume-weighted average price."""
        expr = "TS_Sum($close * $volume, 5) / TS_Sum($volume, 5)"
        indicator = FactorExpIndicator(expr, period=5)
        
        # Feed data with varying volumes
        data = [
            (100.0, 1000.0),
            (102.0, 2000.0),
            (101.0, 1500.0),
            (103.0, 500.0),
            (104.0, 3000.0),
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        # Calculate expected VWAP
        total_value = sum(p * v for p, v in data)
        total_volume = sum(v for _, v in data)
        expected_vwap = total_value / total_volume
        
        assert indicator.value == pytest.approx(expected_vwap, rel=1e-5)
    
    def test_expression_validation(self):
        """Test expression validation catches errors."""
        # Invalid expression
        with pytest.raises(ValueError, match="Failed to parse"):
            FactorExpIndicator("$close +")
        
        # Division by zero
        with pytest.raises(ValueError, match="Division by zero"):
            FactorExpIndicator("$close / 0")
        
        # Unknown operator
        with pytest.raises(ValueError, match="Unknown operator"):
            FactorExpIndicator("UnknownOp($close)")
    
    def test_security_levels(self):
        """Test different security levels."""
        # Trusted mode allows more operators
        config = SecurityConfig.trusted()
        indicator = FactorExpIndicator("Sin($close / 100)", security_config=config)
        indicator.handle_bar(self.create_test_bar(314.159))
        assert abs(indicator.value) < 1.0  # Sin result
        
        # Paranoid mode restricts operators
        config = SecurityConfig.paranoid()
        with pytest.raises(ValueError, match="Forbidden operator"):
            FactorExpIndicator("Sin($close)", security_config=config)
    
    def test_indicator_reset(self):
        """Test indicator reset functionality."""
        indicator = FactorExpIndicator("TS_Mean($close, 3)", period=3)
        
        # Feed some data
        for i in range(5):
            indicator.handle_bar(self.create_test_bar(100.0 + i, timestamp=i))
        
        assert indicator.initialized
        assert indicator.count == 5
        
        # Reset
        indicator.reset()
        
        assert not indicator.initialized
        assert not indicator.has_inputs
        assert indicator.count == 0
        assert indicator.value == 0.0
    
    def test_multiple_features(self):
        """Test expressions using multiple features."""
        # Price range
        expr = "($high - $low) / $close"
        indicator = FactorExpIndicator(expr)
        
        indicator.handle_bar(self.create_test_bar(100.0))
        # With our test bar creation, high=101, low=99, close=100
        expected = (101.0 - 99.0) / 100.0
        assert indicator.value == pytest.approx(expected)
    
    def test_conditional_logic(self):
        """Test conditional operations."""
        # Greater than
        indicator = FactorExpIndicator("Greater($close, 100)")
        
        indicator.handle_bar(self.create_test_bar(105.0))
        assert indicator.value == 1.0
        
        indicator.handle_bar(self.create_test_bar(95.0))
        assert indicator.value == 0.0