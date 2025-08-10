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
Cross-Sectional Momentum Strategy

This strategy demonstrates how to implement a cross-sectional momentum strategy
in Nautilus Trader. It ranks instruments based on their momentum and trades
the top N performers.
"""

from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class CrossSectionalMomentumConfig(StrategyConfig, frozen=True):
    """
    Configuration for `CrossSectionalMomentum` strategy.
    
    Parameters
    ----------
    universe : list[str]
        List of instrument IDs to trade.
    lookback_period : PositiveInt
        Number of bars to calculate momentum.
    rebalance_interval : str
        Pandas frequency string for rebalancing (e.g., '1D', '1W').
    top_n : PositiveInt
        Number of top momentum instruments to hold.
    position_size_pct : PositiveFloat
        Percentage of portfolio per position.
    min_data_points : PositiveInt
        Minimum bars required before trading.
    bar_type_spec : str
        Bar type specification (e.g., '1-MINUTE-LAST').
    """
    
    universe: list[str]
    lookback_period: PositiveInt = 20
    rebalance_interval: str = "1D"
    top_n: PositiveInt = 5
    position_size_pct: PositiveFloat = 0.95
    min_data_points: PositiveInt = 30
    bar_type_spec: str = "1-MINUTE-LAST"


class CrossSectionalMomentum(Strategy):
    """
    Cross-sectional momentum strategy that ranks instruments by momentum
    and trades the top performers.
    
    The strategy:
    1. Calculates momentum for each instrument in the universe
    2. Ranks instruments by momentum
    3. Holds long positions in the top N instruments
    4. Rebalances periodically
    """
    
    def __init__(self, config: CrossSectionalMomentumConfig) -> None:
        super().__init__(config)
        
        # Strategy configuration
        self.universe = [InstrumentId.from_str(s) for s in config.universe]
        self.lookback_period = config.lookback_period
        self.rebalance_interval = pd.Timedelta(config.rebalance_interval)
        self.top_n = min(config.top_n, len(self.universe))
        self.position_size_pct = config.position_size_pct / self.top_n
        self.min_data_points = config.min_data_points
        self.bar_type_spec = config.bar_type_spec
        
        # Data storage
        self.bar_data: dict[InstrumentId, pd.DataFrame] = {}
        self.momentum_scores: dict[InstrumentId, float] = {}
        
        # State tracking
        self.current_holdings: set[InstrumentId] = set()
        self.last_rebalance: Optional[pd.Timestamp] = None
        self.instruments: dict[InstrumentId, Instrument] = {}
        
    def on_start(self) -> None:
        """Initialize the strategy, subscribe to data for all instruments."""
        self.log.info(f"Starting cross-sectional momentum strategy with {len(self.universe)} instruments")
        
        # Subscribe to bar data for all instruments
        for instrument_id in self.universe:
            # Get instrument
            instrument = self.cache.instrument(instrument_id)
            if instrument is None:
                self.log.error(f"Could not find instrument {instrument_id}")
                continue
                
            self.instruments[instrument_id] = instrument
            
            # Create bar type
            bar_type = BarType(
                instrument_id=instrument_id,
                bar_spec=self.bar_type_spec,
                aggregation_source="EXTERNAL",
            )
            
            # Request historical data
            start_time = self.clock.utc_now() - pd.Timedelta(days=max(30, self.lookback_period + 10))
            self.request_bars(bar_type, start=start_time)
            
            # Subscribe to live data
            self.subscribe_bars(bar_type)
            
            # Initialize data storage
            self.bar_data[instrument_id] = pd.DataFrame()
            
    def on_bar(self, bar: Bar) -> None:
        """Process incoming bar data."""
        instrument_id = bar.bar_type.instrument_id
        
        # Update bar data
        self._update_bar_data(instrument_id, bar)
        
        # Check if we should rebalance
        if self._should_rebalance():
            self._rebalance_portfolio()
            
    def _update_bar_data(self, instrument_id: InstrumentId, bar: Bar) -> None:
        """Update the bar data for an instrument."""
        new_data = pd.DataFrame({
            'open': [bar.open.as_double()],
            'high': [bar.high.as_double()],
            'low': [bar.low.as_double()],
            'close': [bar.close.as_double()],
            'volume': [bar.volume.as_double()],
        }, index=[pd.Timestamp(bar.ts_event, tz='UTC')])
        
        # Append to existing data
        if instrument_id in self.bar_data:
            self.bar_data[instrument_id] = pd.concat([
                self.bar_data[instrument_id],
                new_data
            ]).tail(self.min_data_points * 2)  # Keep some extra for safety
        else:
            self.bar_data[instrument_id] = new_data
            
    def _should_rebalance(self) -> bool:
        """Check if it's time to rebalance the portfolio."""
        # Don't rebalance until we have enough data
        if not self._has_sufficient_data():
            return False
            
        current_time = self.clock.utc_now()
        
        # First rebalance
        if self.last_rebalance is None:
            return True
            
        # Check if rebalance interval has passed
        return (current_time - self.last_rebalance) >= self.rebalance_interval
        
    def _has_sufficient_data(self) -> bool:
        """Check if we have enough data for all instruments."""
        for instrument_id in self.universe:
            if instrument_id not in self.bar_data:
                return False
            if len(self.bar_data[instrument_id]) < self.min_data_points:
                return False
        return True
        
    def _calculate_momentum_scores(self) -> None:
        """Calculate momentum scores for all instruments."""
        self.momentum_scores.clear()
        
        for instrument_id in self.universe:
            if instrument_id not in self.bar_data:
                continue
                
            df = self.bar_data[instrument_id]
            if len(df) < self.lookback_period:
                continue
                
            # Calculate simple momentum as percentage return
            current_price = df['close'].iloc[-1]
            past_price = df['close'].iloc[-self.lookback_period]
            
            if past_price > 0:
                momentum = (current_price / past_price - 1) * 100
                self.momentum_scores[instrument_id] = momentum
                
    def _rank_instruments(self) -> list[InstrumentId]:
        """Rank instruments by momentum and return top N."""
        # Calculate latest momentum scores
        self._calculate_momentum_scores()
        
        # Sort by momentum (descending)
        sorted_instruments = sorted(
            self.momentum_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Return top N instrument IDs
        return [inst_id for inst_id, _ in sorted_instruments[:self.top_n]]
        
    def _rebalance_portfolio(self) -> None:
        """Rebalance the portfolio based on momentum rankings."""
        self.log.info("Rebalancing portfolio")
        
        # Get target holdings
        target_holdings = set(self._rank_instruments())
        
        # Log momentum scores
        for inst_id in target_holdings:
            score = self.momentum_scores.get(inst_id, 0)
            self.log.info(f"{inst_id}: momentum = {score:.2f}%")
        
        # Calculate instruments to buy and sell
        to_sell = self.current_holdings - target_holdings
        to_buy = target_holdings - self.current_holdings
        to_hold = self.current_holdings & target_holdings
        
        # Close positions for instruments no longer in top N
        for instrument_id in to_sell:
            self._close_position(instrument_id)
            
        # Adjust positions for instruments still in top N
        for instrument_id in to_hold:
            self._adjust_position(instrument_id)
            
        # Open positions for new instruments in top N
        for instrument_id in to_buy:
            self._open_position(instrument_id)
            
        # Update state
        self.current_holdings = target_holdings
        self.last_rebalance = self.clock.utc_now()
        
    def _calculate_position_size(self, instrument_id: InstrumentId) -> Quantity:
        """Calculate the position size for an instrument."""
        # Get account balance
        account = self.portfolio.account(self.cache.venue_for_instrument(instrument_id))
        if account is None:
            return Quantity.zero()
            
        # Calculate position value
        balance = account.balance_total().as_decimal()
        position_value = balance * Decimal(str(self.position_size_pct))
        
        # Get current price
        last_quote = self.cache.quote_tick(instrument_id)
        if last_quote is None:
            # Fall back to last bar close
            if instrument_id in self.bar_data and len(self.bar_data[instrument_id]) > 0:
                price = Decimal(str(self.bar_data[instrument_id]['close'].iloc[-1]))
            else:
                return Quantity.zero()
        else:
            price = last_quote.ask_price.as_decimal()
            
        # Calculate quantity
        instrument = self.instruments.get(instrument_id)
        if instrument is None:
            return Quantity.zero()
            
        raw_quantity = position_value / price
        quantity = instrument.make_qty(raw_quantity)
        
        return quantity
        
    def _open_position(self, instrument_id: InstrumentId) -> None:
        """Open a new position in the given instrument."""
        # Check if we already have a position
        positions = self.cache.positions_for_instrument(instrument_id)
        if positions:
            self.log.warning(f"Already have position for {instrument_id}")
            return
            
        # Calculate position size
        quantity = self._calculate_position_size(instrument_id)
        if quantity <= 0:
            self.log.warning(f"Invalid quantity for {instrument_id}: {quantity}")
            return
            
        # Submit market order
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=quantity,
        )
        
        self.submit_order(order)
        self.log.info(f"Opening position: {instrument_id} qty={quantity}")
        
    def _close_position(self, instrument_id: InstrumentId) -> None:
        """Close position in the given instrument."""
        positions = self.cache.positions_for_instrument(instrument_id)
        
        for position in positions:
            if position.is_open:
                # Submit order to close position
                order = self.order_factory.market(
                    instrument_id=instrument_id,
                    order_side=OrderSide.SELL if position.is_long else OrderSide.BUY,
                    quantity=position.quantity,
                )
                
                self.submit_order(order)
                self.log.info(f"Closing position: {instrument_id}")
                
    def _adjust_position(self, instrument_id: InstrumentId) -> None:
        """Adjust position size for the given instrument."""
        positions = self.cache.positions_for_instrument(instrument_id)
        if not positions:
            # No position, open a new one
            self._open_position(instrument_id)
            return
            
        # For simplicity, we'll keep existing positions
        # In a real strategy, you might want to rebalance position sizes
        pass
        
    def on_stop(self) -> None:
        """Close all positions when strategy stops."""
        self.log.info("Stopping strategy, closing all positions")
        
        # Close all open positions
        for position in self.cache.positions_open():
            if position.instrument_id in self.universe:
                self._close_position(position.instrument_id)