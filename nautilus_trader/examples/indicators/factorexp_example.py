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
Example of using FactorExp expressions in a Nautilus Trader strategy.

This example demonstrates how to integrate FactorExp's powerful expression
language into your trading strategies.
"""

from decimal import Decimal

from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import OrderSide

# Import FactorExp integration
from nautilus_trader.indicators.factorexp import FactorExpIndicator, SecurityConfig


class FactorExpDemoConfig(StrategyConfig):
    """Configuration for the FactorExp demo strategy."""
    
    instrument_id: InstrumentId
    bar_type: BarType
    fast_period: int = 10
    slow_period: int = 30
    signal_threshold: float = 0.02
    trade_size: Decimal = Decimal("1.0")


class FactorExpDemoStrategy(Strategy):
    """
    A demonstration strategy using FactorExp expressions.
    
    This strategy showcases:
    1. Simple moving average crossover using FactorExp syntax
    2. Momentum calculation
    3. Volatility-adjusted signals
    4. Complex factor combinations
    """
    
    def __init__(self, config: FactorExpDemoConfig):
        """Initialize the strategy."""
        super().__init__(config)
        
        # Store config
        self.instrument_id = config.instrument_id
        self.bar_type = config.bar_type
        self.signal_threshold = config.signal_threshold
        self.trade_size = config.trade_size
        
        # Create FactorExp indicators
        
        # 1. Simple moving average ratio
        self.ma_ratio = FactorExpIndicator(
            expression=f"TS_Mean($close, {config.fast_period}) / TS_Mean($close, {config.slow_period})",
            period=config.slow_period,
            name="MA_Ratio"
        )
        
        # 2. Price momentum
        self.momentum = FactorExpIndicator(
            expression="($close - TS_Ref($close, 5)) / TS_Ref($close, 5)",
            period=5,
            name="Momentum_5"
        )
        
        # 3. Volatility (using standard deviation)
        self.volatility = FactorExpIndicator(
            expression="TS_Std($close, 20)",
            period=20,
            name="Volatility_20"
        )
        
        # 4. Volume-weighted average price
        self.vwap = FactorExpIndicator(
            expression="TS_Sum($close * $volume, 10) / TS_Sum($volume, 10)",
            period=10,
            name="VWAP_10"
        )
        
        # 5. Complex combined signal (Sharpe-like ratio)
        # Note: This would normally use security config for complex expressions
        security_config = SecurityConfig.standard()
        self.combined_signal = FactorExpIndicator(
            expression="""
            (TS_Mean($close, 20) - TS_Mean($close, 50)) / TS_Std($close, 20)
            """,
            period=50,
            security_config=security_config,
            name="TrendStrength"
        )
        
        # Track position state
        self.position_side = None
    
    def on_start(self):
        """Actions to be performed on strategy start."""
        self.log.info("Starting FactorExp demo strategy")
        
        # Register indicators for the bar type
        self.register_indicator_for_bars(self.bar_type, self.ma_ratio)
        self.register_indicator_for_bars(self.bar_type, self.momentum)
        self.register_indicator_for_bars(self.bar_type, self.volatility)
        self.register_indicator_for_bars(self.bar_type, self.vwap)
        self.register_indicator_for_bars(self.bar_type, self.combined_signal)
        
        # Subscribe to bars
        self.subscribe_bars(self.bar_type)
        
        self.log.info(f"Subscribed to {self.bar_type}")
    
    def on_bar(self, bar: Bar):
        """Handle bar data."""
        # Log current bar
        self.log.debug(f"Received bar: {bar}")
        
        # Check if indicators are initialized
        if not all([
            self.ma_ratio.initialized,
            self.momentum.initialized,
            self.volatility.initialized,
            self.combined_signal.initialized
        ]):
            self.log.debug("Waiting for indicators to initialize...")
            return
        
        # Get indicator values
        ma_ratio = self.ma_ratio.value
        momentum = self.momentum.value
        volatility = self.volatility.value
        vwap = self.vwap.value if self.vwap.initialized else bar.close.as_double()
        signal = self.combined_signal.value
        
        # Log indicator values
        self.log.info(
            f"Indicators - MA Ratio: {ma_ratio:.4f}, "
            f"Momentum: {momentum:.4f}, Vol: {volatility:.4f}, "
            f"Signal: {signal:.4f}"
        )
        
        # Trading logic
        self._execute_trading_logic(bar, ma_ratio, momentum, signal)
    
    def _execute_trading_logic(self, bar: Bar, ma_ratio: float, momentum: float, signal: float):
        """Execute trading logic based on indicators."""
        # Get current position
        position = self.portfolio.position(self.instrument_id)
        
        # Entry logic
        if position is None or position.is_closed:
            # Long entry: MA ratio > 1 and positive momentum and strong signal
            if ma_ratio > 1.0 and momentum > self.signal_threshold and signal > 1.0:
                self._enter_long(bar)
                
            # Short entry: MA ratio < 1 and negative momentum and weak signal
            elif ma_ratio < 1.0 and momentum < -self.signal_threshold and signal < -1.0:
                self._enter_short(bar)
        
        # Exit logic
        elif position.is_open:
            # Exit long: MA ratio crosses below 0.99 or signal weakens
            if position.is_long and (ma_ratio < 0.99 or signal < 0):
                self._exit_position(position, bar, "Exit long signal")
                
            # Exit short: MA ratio crosses above 1.01 or signal strengthens  
            elif position.is_short and (ma_ratio > 1.01 or signal > 0):
                self._exit_position(position, bar, "Exit short signal")
    
    def _enter_long(self, bar: Bar):
        """Enter a long position."""
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self.position_side = OrderSide.BUY
        self.log.info(f"Entered LONG at {bar.close}")
    
    def _enter_short(self, bar: Bar):
        """Enter a short position."""
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self.position_side = OrderSide.SELL
        self.log.info(f"Entered SHORT at {bar.close}")
    
    def _exit_position(self, position, bar: Bar, reason: str):
        """Exit the current position."""
        if position.is_long:
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=position.quantity,
            )
        else:
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=position.quantity,
            )
        
        self.submit_order(order)
        self.position_side = None
        self.log.info(f"Exited position at {bar.close} - {reason}")
    
    def on_stop(self):
        """Actions to be performed on strategy stop."""
        # Close any open positions
        position = self.portfolio.position(self.instrument_id)
        if position and position.is_open:
            self.close_position(self.instrument_id)
            
        self.log.info("Stopped FactorExp demo strategy")