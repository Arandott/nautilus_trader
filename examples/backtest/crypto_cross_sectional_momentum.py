#!/usr/bin/env python3
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

"""
Example backtest for cross-sectional momentum strategy using crypto instruments.
"""

import pandas as pd
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import BacktestDataConfig
from nautilus_trader.config import BacktestVenueConfig
from nautilus_trader.config import BacktestRunConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.examples.strategies.cross_sectional_momentum import CrossSectionalMomentum
from nautilus_trader.examples.strategies.cross_sectional_momentum import CrossSectionalMomentumConfig
from nautilus_trader.persistence.catalog import ParquetDataCatalog


def run_backtest():
    """Run the cross-sectional momentum backtest."""
    
    # Configure backtest engine
    config = BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=LoggingConfig(log_level="INFO"),
    )
    
    # Build the backtest engine
    engine = BacktestEngine(config)
    
    # Add a trading venue (using Binance as example)
    BINANCE = Venue("BINANCE")
    engine.add_venue(
        venue=BINANCE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.SPOT,
        base_currency=None,  # Multi-currency account
        starting_balances=[
            Money(10_000, USDT),  # Starting with 10,000 USDT
        ],
    )
    
    # Define the universe of crypto instruments
    # In a real scenario, you would load actual crypto pairs
    universe = [
        "BTCUSDT.BINANCE",
        "ETHUSDT.BINANCE",
        "BNBUSDT.BINANCE",
        "ADAUSDT.BINANCE",
        "XRPUSDT.BINANCE",
        "SOLUSDT.BINANCE",
        "DOTUSDT.BINANCE",
        "MATICUSDT.BINANCE",
        "LINKUSDT.BINANCE",
        "AVAXUSDT.BINANCE",
    ]
    
    # Configure the strategy
    strategy_config = CrossSectionalMomentumConfig(
        universe=universe,
        lookback_period=20,  # 20 bars for momentum calculation
        rebalance_interval="1D",  # Daily rebalancing
        top_n=3,  # Hold top 3 momentum cryptos
        position_size_pct=0.9,  # Use 90% of capital
        min_data_points=30,  # Need 30 bars before trading
        bar_type_spec="1-HOUR-LAST",  # Use hourly bars
    )
    
    # Initialize strategy
    strategy = CrossSectionalMomentum(config=strategy_config)
    
    # Add strategy to engine
    engine.add_strategy(strategy)
    
    # Load and add instrument data
    # Note: In a real implementation, you would load actual historical data
    # This is a placeholder showing the structure
    
    # Example of loading data from a catalog (if you have one)
    # catalog = ParquetDataCatalog("path/to/catalog")
    
    # For each instrument in the universe
    # for instrument_id_str in universe:
    #     instrument_id = InstrumentId.from_str(instrument_id_str)
    #     
    #     # Load instrument
    #     instrument = catalog.instruments(instrument_ids=[instrument_id_str])[0]
    #     engine.add_instrument(instrument)
    #     
    #     # Load bars
    #     bar_type = BarType.from_str(f"{instrument_id_str}-1-HOUR-LAST-EXTERNAL")
    #     bars = catalog.bars(bar_types=[str(bar_type)])[bar_type]
    #     engine.add_data(bars)
    
    # Run the backtest
    engine.run()
    
    # Get results
    result = engine.trader.portfolio.performance
    
    # Print results
    print("=" * 80)
    print("CROSS-SECTIONAL MOMENTUM STRATEGY RESULTS")
    print("=" * 80)
    print(f"Total Return: {result.total.pnl:,.2f} USDT")
    print(f"Total Return %: {result.total.returns * 100:.2f}%")
    print(f"Max Drawdown: {result.max_drawdown * 100:.2f}%")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Win Rate: {result.win_rate * 100:.2f}%")
    print(f"Total Trades: {result.total_trades}")
    print("=" * 80)
    
    # Generate and display more detailed statistics
    stats = engine.trader.generate_statistics()
    print("\nDetailed Statistics:")
    for stat in stats:
        print(f"{stat.name}: {stat.value}")
    
    # You can also access individual positions and orders
    positions = engine.cache.positions()
    print(f"\nTotal positions: {len(positions)}")
    
    orders = engine.cache.orders()
    print(f"Total orders: {len(orders)}")
    
    return engine


def create_synthetic_data_example():
    """
    Create synthetic data for demonstration purposes.
    In production, you would load real historical data.
    """
    from nautilus_trader.test_kit.providers import TestDataProvider
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Price, Quantity
    
    # This is just an example structure
    # You would need to implement actual data loading
    
    instruments = []
    bars_data = {}
    
    # Example instrument creation
    btcusdt = CurrencyPair(
        instrument_id="BTCUSDT.BINANCE",
        raw_symbol="BTCUSDT",
        base_currency=ETH,  # Should be BTC
        quote_currency=USDT,
        price_precision=2,
        size_precision=8,
        price_increment=Price(0.01, precision=2),
        size_increment=Quantity(0.00000001, precision=8),
        lot_size=Quantity(1, precision=0),
        max_quantity=Quantity(9000, precision=0),
        min_quantity=Quantity(0.00001, precision=8),
        max_price=Price(1000000, precision=2),
        min_price=Price(0.01, precision=2),
    )
    
    # Add more instruments...
    
    return instruments, bars_data


if __name__ == "__main__":
    # Run the backtest
    engine = run_backtest()
    
    # Note: This example requires actual historical data to run
    # You would need to:
    # 1. Set up a data catalog with historical crypto data
    # 2. Load instruments and price data for the universe
    # 3. Run the backtest with real data
    
    print("\nNote: This example requires historical data to run properly.")
    print("Please load actual crypto data using ParquetDataCatalog or similar.")