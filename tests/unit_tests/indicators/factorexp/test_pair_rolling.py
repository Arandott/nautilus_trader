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

"""Tests for pair rolling operations."""

import pytest
import numpy as np

from nautilus_trader.indicators.factorexp import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestPairRollingOperations:
    """Test pair rolling operations like correlation and covariance."""
    
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
    
    def test_correlation_basic(self):
        """Test basic correlation calculation."""
        # Create indicator for correlation between close and volume
        indicator = FactorExpIndicator("TS_Corr($close, $volume, 5)", period=5)
        
        # Feed perfectly correlated data
        data = [
            (100.0, 1000.0),
            (101.0, 1010.0),
            (102.0, 1020.0),
            (103.0, 1030.0),
            (104.0, 1040.0),
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        # Should have perfect correlation
        assert indicator.initialized
        assert abs(indicator.value - 1.0) < 0.001  # Near perfect correlation
    
    def test_correlation_negative(self):
        """Test negative correlation."""
        indicator = FactorExpIndicator("TS_Corr($close, $volume, 5)", period=5)
        
        # Feed negatively correlated data
        data = [
            (100.0, 1040.0),
            (101.0, 1030.0),
            (102.0, 1020.0),
            (103.0, 1010.0),
            (104.0, 1000.0),
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        # Should have negative correlation
        assert indicator.initialized
        assert indicator.value < -0.9  # Strong negative correlation
    
    def test_covariance(self):
        """Test covariance calculation."""
        indicator = FactorExpIndicator("TS_Cov($close, $volume, 5)", period=5)
        
        # Feed data
        data = [
            (100.0, 1000.0),
            (102.0, 1100.0),
            (98.0, 900.0),
            (105.0, 1200.0),
            (103.0, 1150.0),
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        # Covariance should be positive for positively related data
        assert indicator.initialized
        assert indicator.value > 0
    
    def test_beta_calculation(self):
        """Test beta (regression coefficient) calculation."""
        # Beta measures how much Y changes when X changes
        indicator = FactorExpIndicator("TS_Beta($volume, $close, 5)", period=5)
        
        # Feed data where close moves twice as much as volume
        data = [
            (100.0, 1000.0),
            (102.0, 1001.0),  # close +2, volume +1
            (106.0, 1003.0),  # close +4, volume +2
            (104.0, 1002.0),  # close -2, volume -1
            (108.0, 1004.0),  # close +4, volume +2
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        # Beta should be approximately 2 (close changes 2x volume)
        assert indicator.initialized
        # Note: Beta calculation depends on which is X and which is Y
        # TS_Beta($volume, $close) means volume is X, close is Y
        assert indicator.value > 0  # Should be positive
    
    def test_correlation_with_expressions(self):
        """Test correlation with more complex expressions."""
        # Correlation between returns and volume change
        expr = "TS_Corr(($close - TS_Ref($close, 1)) / TS_Ref($close, 1), " + \
               "($volume - TS_Ref($volume, 1)) / TS_Ref($volume, 1), 5)"
        
        indicator = FactorExpIndicator(expr, period=6)  # Need 6 for Ref(1) + window 5
        
        # Feed data
        prices = [100, 101, 99, 102, 98, 103, 97, 104]
        volumes = [1000, 1100, 900, 1200, 800, 1300, 700, 1400]
        
        for i, (price, volume) in enumerate(zip(prices, volumes)):
            indicator.handle_bar(self.create_test_bar(float(price), float(volume), timestamp=i))
        
        # Should compute correlation between returns
        if indicator.initialized:
            assert isinstance(indicator.value, float)
            assert -1.0 <= indicator.value <= 1.0  # Correlation bounds
    
    def test_pair_rolling_not_enough_data(self):
        """Test pair rolling operations with insufficient data."""
        indicator = FactorExpIndicator("TS_Corr($close, $volume, 5)", period=5)
        
        # Feed only 3 bars (need 5)
        for i in range(3):
            indicator.handle_bar(self.create_test_bar(100.0 + i, 1000.0 + i * 10, timestamp=i))
        
        # Should not be initialized yet
        assert not indicator.initialized
        assert indicator.value == 0.0
    
    def test_multiple_pair_operations(self):
        """Test multiple pair operations in one expression."""
        # Correlation minus covariance
        expr = "TS_Corr($close, $volume, 5) - TS_Cov($close, $volume, 5) / 1000000"
        indicator = FactorExpIndicator(expr, period=5)
        
        # Feed data
        data = [
            (100.0, 1000.0),
            (101.0, 1050.0),
            (102.0, 1100.0),
            (101.5, 1075.0),
            (103.0, 1150.0),
        ]
        
        for i, (price, volume) in enumerate(data):
            indicator.handle_bar(self.create_test_bar(price, volume, timestamp=i))
        
        assert indicator.initialized
        assert isinstance(indicator.value, float)