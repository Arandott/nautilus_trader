#!/usr/bin/env python3
"""
Multi-instrument demonstration of FactorExp integration.

This example shows how to use cross-sectional operations across
multiple instruments for factor-based trading strategies.
"""

import numpy as np
from datetime import datetime

from nautilus_trader.indicators.factorexp import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


class MultiInstrumentFactorDemo:
    """Demonstrates multi-instrument factor computations."""
    
    def __init__(self):
        """Initialize the demo."""
        self.venue = Venue("SIM")
        self.symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]
        self.indicators = {}
        
    def create_bar(self, symbol: str, price: float, volume: float, timestamp: int) -> Bar:
        """Create a bar for a specific symbol."""
        instrument_id = InstrumentId(Symbol(symbol), self.venue)
        bar_type = BarType(
            instrument_id=instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE),
            aggregation_source=AggregationSource.EXTERNAL,
        )
        
        return Bar(
            bar_type=bar_type,
            open=Price.from_str(str(price * 0.99)),
            high=Price.from_str(str(price * 1.01)),
            low=Price.from_str(str(price * 0.98)),
            close=Price.from_str(str(price)),
            volume=Quantity.from_str(str(volume)),
            ts_event=timestamp,
            ts_init=timestamp,
        )
    
    def setup_indicators(self):
        """Set up various multi-instrument indicators."""
        # 1. Cross-sectional momentum
        self.indicators["momentum_rank"] = FactorExpIndicator(
            "CSRank(($close - TS_Ref($close, 20)) / TS_Ref($close, 20))",
            period=20,
            multi_instrument=True,
            name="MomentumRank"
        )
        
        # 2. Relative volume
        self.indicators["volume_zscore"] = FactorExpIndicator(
            "ZScore($volume / TS_Mean($volume, 10))",
            period=10,
            multi_instrument=True,
            name="RelativeVolumeZ"
        )
        
        # 3. Mean reversion factor
        self.indicators["mean_reversion"] = FactorExpIndicator(
            "Demean(($close - TS_Mean($close, 20)) / TS_Std($close, 20))",
            period=20,
            multi_instrument=True,
            name="MeanReversionFactor"
        )
        
        # 4. Pair correlation
        self.indicators["correlation"] = FactorExpIndicator(
            "TS_Corr($close, $volume, 15)",
            period=15,
            name="PriceVolumeCorr"
        )
        
        # 5. Combined alpha factor
        self.indicators["alpha"] = FactorExpIndicator(
            "CSRank(0.4 * TS_Mean($close, 10) / TS_Std($close, 10) + " +
            "0.6 * ($close - TS_Ref($close, 5)) / TS_Ref($close, 5))",
            period=10,
            multi_instrument=True,
            name="AlphaFactor"
        )
    
    def generate_market_data(self):
        """Generate synthetic market data for demonstration."""
        np.random.seed(42)
        
        # Base prices for each symbol
        base_prices = {
            "AAPL": 150.0,
            "GOOGL": 2800.0,
            "MSFT": 300.0,
            "AMZN": 3200.0,
            "META": 200.0,
        }
        
        # Generate 30 time periods
        for t in range(30):
            timestamp = t * 60_000_000_000  # 1 minute intervals in nanoseconds
            
            print(f"\n=== Time Period {t} ===")
            
            # Generate bars for all symbols at this timestamp
            bars = []
            for symbol in self.symbols:
                # Add some random walk to prices
                drift = 0.001 if symbol in ["AAPL", "MSFT"] else -0.0005
                volatility = 0.01
                
                price_change = np.random.normal(drift, volatility)
                base_prices[symbol] *= (1 + price_change)
                
                # Volume with some correlation to price changes
                base_volume = 1_000_000
                volume = base_volume * (1 + abs(price_change) * 10 + np.random.normal(0, 0.2))
                
                bar = self.create_bar(symbol, base_prices[symbol], volume, timestamp)
                bars.append((symbol, bar))
            
            # Process bars through indicators
            results = {symbol: {} for symbol in self.symbols}
            
            for symbol, bar in bars:
                # Update all indicators
                for name, indicator in self.indicators.items():
                    indicator.handle_bar(bar)
                    
                    # Store result if initialized
                    if indicator.initialized:
                        results[symbol][name] = indicator.value
            
            # Display results for this time period
            if t >= 20:  # After warm-up period
                print("\nFactor Values:")
                print(f"{'Symbol':<8} {'Mom Rank':<10} {'Vol Z':<10} {'MeanRev':<10} {'Alpha':<10}")
                print("-" * 48)
                
                for symbol in self.symbols:
                    if results[symbol]:
                        mom = results[symbol].get("momentum_rank", "N/A")
                        vol = results[symbol].get("volume_zscore", "N/A")
                        mr = results[symbol].get("mean_reversion", "N/A")
                        alpha = results[symbol].get("alpha", "N/A")
                        
                        print(f"{symbol:<8} {mom:<10.3f} {vol:<10.3f} {mr:<10.3f} {alpha:<10.3f}"
                              if isinstance(mom, float) else f"{symbol:<8} {'N/A':<10} {'N/A':<10} {'N/A':<10} {'N/A':<10}")
    
    def demonstrate_portfolio_construction(self):
        """Show how to use factors for portfolio construction."""
        print("\n" + "=" * 60)
        print("Portfolio Construction Example")
        print("=" * 60)
        
        print("""
Using the alpha factor for ranking:
- Top ranked (Alpha > 0.8): Strong BUY
- High ranked (Alpha > 0.6): BUY
- Middle ranked (0.4 < Alpha < 0.6): HOLD
- Low ranked (Alpha < 0.4): SELL/SHORT

The mean reversion factor identifies oversold/overbought:
- MeanRev < -1.5: Oversold (potential BUY)
- MeanRev > 1.5: Overbought (potential SELL)

Volume Z-score indicates unusual activity:
- |Vol Z| > 2: Significant volume anomaly
        """)
    
    def run(self):
        """Run the complete demonstration."""
        print("=" * 60)
        print("Multi-Instrument FactorExp Demo")
        print("=" * 60)
        
        # Set up indicators
        self.setup_indicators()
        print(f"\nCreated {len(self.indicators)} factor indicators")
        
        # Generate and process market data
        self.generate_market_data()
        
        # Show portfolio construction
        self.demonstrate_portfolio_construction()
        
        print("\n" + "=" * 60)
        print("Demo Complete!")
        print("=" * 60)


def main():
    """Run the demonstration."""
    demo = MultiInstrumentFactorDemo()
    demo.run()


if __name__ == "__main__":
    main()