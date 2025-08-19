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
FactorExp EMA Cross Strategy Backtest Example

This example demonstrates how to use FactorExp expressions within a Nautilus Trader
backtesting environment. The strategy showcases the power of FactorExp by using
complex mathematical expressions for technical analysis instead of traditional indicators.

Features demonstrated:
1. FactorExp EMA ratio calculations
2. Volatility filtering using FactorExp expressions  
3. Momentum analysis with FactorExp
4. Trend strength calculations
5. Integration with Nautilus Trader's backtesting framework

To run this example:
    python examples/backtest/factorexp/factorexp_ema_cross_ethusdt.py
"""

import time
from decimal import Decimal

import pandas as pd

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import TradeTickDataWrangler
from nautilus_trader.test_kit.providers import TestDataProvider
from nautilus_trader.test_kit.providers import TestInstrumentProvider

# Import our FactorExp strategy
from examples.backtest.factorexp.factorexp_ema_cross_strategy import FactorExpEMACross
from examples.backtest.factorexp.factorexp_ema_cross_strategy import FactorExpEMACrossConfig


def main():
    """
    Run the FactorExp EMA Cross strategy backtest.
    
    This function demonstrates:
    1. Setting up a backtest environment with Nautilus Trader
    2. Loading market data from the test dataset
    3. Configuring and running a FactorExp-based strategy
    4. Analyzing the results
    """
    print("=" * 80)
    print("FactorExp EMA Cross Strategy Backtest")
    print("=" * 80)
    print()
    print("This example demonstrates FactorExp integration with Nautilus Trader.")
    print("The strategy uses complex FactorExp expressions for:")
    print("  • EMA ratio calculations (fast/slow EMA)")
    print("  • Volatility filtering (rolling std / rolling mean)")  
    print("  • Momentum analysis (price deviation from moving average)")
    print("  • Trend strength (EMA difference as percentage)")
    print()

    # Configure backtest engine
    config = BacktestEngineConfig(trader_id=TraderId("FACTOREXP-001"))

    # Build the backtest engine
    engine = BacktestEngine(config=config)

    # Add a trading venue (Binance spot exchange)
    engine.add_venue(
        venue=BINANCE_VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,  # Spot CASH account
        base_currency=None,  # Multi-currency account
        starting_balances=[Money(100_000, USDT), Money(10, ETH)],
    )

    # Add instruments
    ETHUSDT_BINANCE = TestInstrumentProvider.ethusdt_binance()
    engine.add_instrument(ETHUSDT_BINANCE)

    # Add market data
    print("Loading market data...")
    provider = TestDataProvider()
    wrangler = TradeTickDataWrangler(instrument=ETHUSDT_BINANCE)
    ticks = wrangler.process(provider.read_csv_ticks("binance/ethusdt-trades.csv"))
    engine.add_data(ticks)
    print(f"Loaded {len(ticks)} trade ticks")

    # Configure the FactorExp strategy
    strategy_config = FactorExpEMACrossConfig(
        instrument_id=ETHUSDT_BINANCE.id,
        bar_type=BarType.from_str("ETHUSDT.BINANCE-100-TICK-LAST-INTERNAL"),
        trade_size=Decimal("0.10"),
        fast_ema_period=10,      # Fast EMA period
        slow_ema_period=20,      # Slow EMA period
        volatility_period=20,    # Volatility calculation period
        volatility_threshold=0.001,  # Minimum volatility for trading (0.1%)
    )

    # Instantiate and add the strategy
    strategy = FactorExpEMACross(config=strategy_config)
    engine.add_strategy(strategy=strategy)

    print()
    print("Strategy Configuration:")
    print(f"  • Instrument: {strategy_config.instrument_id}")
    print(f"  • Bar Type: {strategy_config.bar_type}")
    print(f"  • Trade Size: {strategy_config.trade_size}")
    print(f"  • Fast EMA Period: {strategy_config.fast_ema_period}")
    print(f"  • Slow EMA Period: {strategy_config.slow_ema_period}")
    print(f"  • Volatility Period: {strategy_config.volatility_period}")
    print(f"  • Volatility Threshold: {strategy_config.volatility_threshold:.1%}")
    print()

    print("FactorExp Expressions Used:")
    print(f"  • EMA Ratio: TS_Mean($close, {strategy_config.fast_ema_period}) / TS_Mean($close, {strategy_config.slow_ema_period})")
    print(f"  • Volatility: TS_Std($close, {strategy_config.volatility_period}) / TS_Mean($close, {strategy_config.volatility_period})")
    print(f"  • Momentum: ($close - TS_Mean($close, {strategy_config.slow_ema_period})) / TS_Mean($close, {strategy_config.slow_ema_period})")
    print(f"  • Trend Strength: (TS_Mean($close, {strategy_config.fast_ema_period}) - TS_Mean($close, {strategy_config.slow_ema_period})) / TS_Mean($close, {strategy_config.slow_ema_period})")
    print()

    # Pause before running (optional)
    time.sleep(0.1)
    input("Press Enter to start the backtest...")

    # Run the backtest
    print("Running backtest...")
    start_time = time.time()
    engine.run()
    elapsed_time = time.time() - start_time

    print(f"Backtest completed in {elapsed_time:.2f} seconds")
    print()

    # Generate and display reports
    print("=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)

    # Configure pandas display options for better report formatting
    with pd.option_context(
        "display.max_rows", 100,
        "display.max_columns", None,
        "display.width", 300,
        "display.precision", 6,
    ):
        # Account report
        print("ACCOUNT REPORT")
        print("-" * 40)
        account_report = engine.trader.generate_account_report(BINANCE_VENUE)
        print(account_report)
        print()

        # Order fills report
        print("ORDER FILLS REPORT")
        print("-" * 40)
        fills_report = engine.trader.generate_order_fills_report()
        print(fills_report)
        print()

        # Positions report
        print("POSITIONS REPORT")
        print("-" * 40)
        positions_report = engine.trader.generate_positions_report()
        print(positions_report)
        print()

    # Additional FactorExp-specific analysis
    print("FACTOREXP STRATEGY ANALYSIS")
    print("-" * 40)
    
    # Get strategy instance to access indicator values
    strategy_instance = engine.trader.strategies()[0]
    
    print("Final Indicator Values:")
    if strategy_instance.ema_ratio.initialized:
        print(f"  • EMA Ratio: {strategy_instance.ema_ratio.value:.6f}")
        print(f"  • Volatility: {strategy_instance.volatility.value:.6f}")
        print(f"  • Momentum: {strategy_instance.momentum.value:.6f}")
        print(f"  • Trend Strength: {strategy_instance.trend_strength.value:.6f}")
    else:
        print("  • Indicators not fully initialized")
    
    print(f"  • Total Bars Processed: {engine.cache.bar_count(strategy_config.bar_type)}")
    print(f"  • EMA Ratio Period: {strategy_instance.ema_ratio.period}")
    print(f"  • Volatility Period: {strategy_instance.volatility.period}")
    print()

    print("Strategy Highlights:")
    print("  • Used FactorExp expressions instead of traditional indicators")
    print("  • Demonstrated complex ratio and volatility calculations")
    print("  • Showed integration between FactorExp and Nautilus Trader")
    print("  • Leveraged high-performance Rust backend for computations")
    print()

    # Reset and cleanup
    engine.reset()
    engine.dispose()

    print("=" * 80)
    print("FactorExp backtest example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()