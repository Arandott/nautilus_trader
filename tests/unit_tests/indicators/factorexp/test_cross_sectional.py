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

"""Tests for cross-sectional operations integration."""

import pytest
import numpy as np

from nautilus_trader.indicators.factorexp import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class TestCrossSectionalIntegration:
    """Test cross-sectional operations with multi-instrument support."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.venue = Venue("TEST")
        
    def create_test_bar(
        self,
        symbol: str,
        close: float,
        volume: float = 1000.0,
        timestamp: int = 0,
    ) -> Bar:
        """Create a test bar for a specific symbol."""
        instrument_id = InstrumentId(Symbol(symbol), self.venue)
        bar_type = BarType(
            instrument_id=instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
        return Bar(
            bar_type=bar_type,
            open=Price.from_str(str(close)),
            high=Price.from_str(str(close * 1.01)),
            low=Price.from_str(str(close * 0.99)),
            close=Price.from_str(str(close)),
            volume=Quantity.from_str(str(volume)),
            ts_event=timestamp,
            ts_init=timestamp,
        )
    
    def test_single_instrument_mode(self):
        """Test that single instrument mode works without cross-sectional manager."""
        # Create indicator without multi-instrument flag
        indicator = FactorExpIndicator("CSRank($close)")
        
        bar = self.create_test_bar("AAPL", 150.0)
        indicator.handle_bar(bar)
        
        # Should return default rank of 0.5
        assert indicator.value == 0.5
    
    def test_multi_instrument_rank(self):
        """Test cross-sectional ranking across multiple instruments."""
        # Create indicator with multi-instrument support
        indicator = FactorExpIndicator("CSRank($close)", multi_instrument=True)
        
        # Feed data for multiple instruments at same timestamp
        timestamp = 1000000
        bars = [
            self.create_test_bar("AAPL", 150.0, timestamp=timestamp),
            self.create_test_bar("GOOGL", 100.0, timestamp=timestamp),
            self.create_test_bar("MSFT", 200.0, timestamp=timestamp),
        ]
        
        # Process bars and store results
        results = {}
        for bar in bars:
            indicator.handle_bar(bar)
            symbol = str(bar.bar_type.instrument_id.symbol)
            results[symbol] = indicator.value
        
        # Check ranks (GOOGL < AAPL < MSFT)
        assert results["GOOGL"] == 0.0  # Lowest
        assert results["AAPL"] == 0.5   # Middle
        assert results["MSFT"] == 1.0   # Highest
    
    def test_multi_instrument_zscore(self):
        """Test cross-sectional z-score calculation."""
        indicator = FactorExpIndicator("ZScore($close)", multi_instrument=True)
        
        # Feed data with known distribution
        timestamp = 2000000
        bars = [
            self.create_test_bar("A", 90.0, timestamp=timestamp),
            self.create_test_bar("B", 100.0, timestamp=timestamp),
            self.create_test_bar("C", 110.0, timestamp=timestamp),
        ]
        
        results = {}
        for bar in bars:
            indicator.handle_bar(bar)
            symbol = str(bar.bar_type.instrument_id.symbol)
            results[symbol] = indicator.value
        
        # Mean should be 100, std should be 10
        # Z-scores should be approximately -1, 0, 1
        assert abs(results["A"] - (-1.0)) < 0.1
        assert abs(results["B"] - 0.0) < 0.1
        assert abs(results["C"] - 1.0) < 0.1
    
    def test_multi_instrument_demean(self):
        """Test cross-sectional demeaning."""
        indicator = FactorExpIndicator("Demean($close)", multi_instrument=True)
        
        # Feed data
        timestamp = 3000000
        bars = [
            self.create_test_bar("X", 80.0, timestamp=timestamp),
            self.create_test_bar("Y", 100.0, timestamp=timestamp),
            self.create_test_bar("Z", 120.0, timestamp=timestamp),
        ]
        
        results = {}
        for bar in bars:
            indicator.handle_bar(bar)
            symbol = str(bar.bar_type.instrument_id.symbol)
            results[symbol] = indicator.value
        
        # Mean is 100, so demeaned values should be -20, 0, 20
        assert abs(results["X"] - (-20.0)) < 0.01
        assert abs(results["Y"] - 0.0) < 0.01
        assert abs(results["Z"] - 20.0) < 0.01
    
    def test_time_alignment(self):
        """Test that time alignment works with tolerance."""
        # 10ms tolerance
        indicator = FactorExpIndicator(
            "CSRank($close)",
            multi_instrument=True,
            time_tolerance_ns=10_000_000
        )
        
        # Feed data with slightly different timestamps
        base_time = 1000000000
        bars = [
            self.create_test_bar("A", 100.0, timestamp=base_time),
            self.create_test_bar("B", 150.0, timestamp=base_time + 5_000_000),  # 5ms later
            self.create_test_bar("C", 200.0, timestamp=base_time + 9_000_000),  # 9ms later
        ]
        
        for bar in bars:
            indicator.handle_bar(bar)
        
        # All should be grouped in same cross-section
        assert indicator.initialized
    
    def test_complex_cross_sectional_expression(self):
        """Test complex expression with cross-sectional operations."""
        # Z-score of moving average
        expr = "ZScore(TS_Mean($close, 3))"
        indicator = FactorExpIndicator(expr, period=3, multi_instrument=True)
        
        # Feed multiple bars for each instrument
        symbols = ["AA", "BB", "CC"]
        prices = {
            "AA": [100, 102, 104],
            "BB": [200, 198, 196],
            "CC": [150, 150, 150],
        }
        
        # Process bars
        for i in range(3):
            timestamp = i * 1000000
            for symbol in symbols:
                bar = self.create_test_bar(
                    symbol,
                    prices[symbol][i],
                    timestamp=timestamp
                )
                indicator.handle_bar(bar)
        
        # After 3 bars, check that we get reasonable z-scores
        assert indicator.initialized
        # Final value is z-score for last processed instrument