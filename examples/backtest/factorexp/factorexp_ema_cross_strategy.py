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

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.events import PositionChanged
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.events import PositionOpened
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


# *** THIS IS A DEMONSTRATION STRATEGY SHOWCASING FACTOREXP CAPABILITIES ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***


class FactorExpEMACrossConfig(StrategyConfig, frozen=True):
    """
    Configuration for ``FactorExpEMACross`` instances.

    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument ID for the strategy.
    bar_type : BarType
        The bar type for the strategy.
    trade_size : Decimal
        The position size per trade.
    fast_ema_period : PositiveInt, default 10
        The fast EMA period.
    slow_ema_period : PositiveInt, default 20
        The slow EMA period.
    volatility_period : PositiveInt, default 20
        The period for volatility calculation.
    volatility_threshold : PositiveFloat, default 0.001
        The minimum volatility threshold for trading.

    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    fast_ema_period: PositiveInt = 10
    slow_ema_period: PositiveInt = 20
    volatility_period: PositiveInt = 20
    volatility_threshold: PositiveFloat = 0.001


class FactorExpEMACross(Strategy):
    """
    A demonstration strategy using FactorExp expressions for EMA cross trading.

    This strategy showcases the power of FactorExp by using complex expressions
    instead of individual indicators. It demonstrates:

    1. Basic EMA cross signals using FactorExp expressions
    2. Volatility filtering to avoid trading in low-volatility periods
    3. Complex ratio calculations for momentum detection
    4. Multiple FactorExp indicators working together

    The strategy enters long when the fast EMA crosses above the slow EMA
    in a sufficiently volatile market, and enters short when the fast EMA
    crosses below the slow EMA.

    Parameters
    ----------
    config : FactorExpEMACrossConfig
        The configuration for the instance.

    Raises
    ------
    ValueError
        If `config.fast_ema_period` is not less than `config.slow_ema_period`.

    """

    def __init__(self, config: FactorExpEMACrossConfig) -> None:
        PyCondition.is_true(
            config.fast_ema_period < config.slow_ema_period,
            f"{config.fast_ema_period=} must be less than {config.slow_ema_period=}",
        )
        super().__init__(config)

        # Initialized in on_start
        self.instrument: Instrument | None = None

        # Create FactorExp indicators to demonstrate various capabilities
        
        # 1. EMA Ratio: Shows relative position of fast vs slow EMA
        self.ema_ratio = FactorExpIndicator(
            f"TS_Mean($close, {config.fast_ema_period}) / TS_Mean($close, {config.slow_ema_period})",
            name="EMA_Ratio"
        )
        
        # 2. Volatility: Rolling standard deviation normalized by price
        self.volatility = FactorExpIndicator(
            f"TS_Std($close, {config.volatility_period}) / TS_Mean($close, {config.volatility_period})",
            name="Volatility"
        )
        
        # 3. Momentum: Price change relative to moving average
        self.momentum = FactorExpIndicator(
            f"($close - TS_Mean($close, {config.slow_ema_period})) / TS_Mean($close, {config.slow_ema_period})",
            name="Momentum"
        )
        
        # 4. Trend Strength: Difference between EMAs as percentage of slow EMA
        self.trend_strength = FactorExpIndicator(
            f"(TS_Mean($close, {config.fast_ema_period}) - TS_Mean($close, {config.slow_ema_period})) / TS_Mean($close, {config.slow_ema_period})",
            name="Trend_Strength"
        )

        # Track previous values for cross detection
        self.prev_ema_ratio = None
        self.position_entry_bar = None

    def on_start(self) -> None:
        """
        Actions to be performed on strategy start.
        """
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return

        # Register all FactorExp indicators for automatic bar updates
        self.register_indicator_for_bars(self.config.bar_type, self.ema_ratio)
        self.register_indicator_for_bars(self.config.bar_type, self.volatility)
        self.register_indicator_for_bars(self.config.bar_type, self.momentum)
        self.register_indicator_for_bars(self.config.bar_type, self.trend_strength)

        # Get historical data
        self.request_bars(self.config.bar_type)

        # Subscribe to live data
        self.subscribe_bars(self.config.bar_type)

    def on_stop(self) -> None:
        """
        Actions to be performed when the strategy is stopped.
        """
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

        # Unsubscribe from data
        self.unsubscribe_bars(self.config.bar_type)

    def on_reset(self) -> None:
        """
        Actions to be performed when the strategy is reset.
        """
        # Reset all FactorExp indicators
        self.ema_ratio.reset()
        self.volatility.reset()
        self.momentum.reset()
        self.trend_strength.reset()
        
        # Reset state
        self.prev_ema_ratio = None
        self.position_entry_bar = None

    def on_instrument(self, instrument: Instrument) -> None:
        """
        Actions to be performed when the strategy is running and receives an instrument.
        """
        pass

    def on_order_book(self, order_book: OrderBook) -> None:
        """
        Actions to be performed when the strategy is running and receives an order book.
        """
        pass

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """
        Actions to be performed when the strategy is running and receives a quote tick.
        """
        pass

    def on_trade_tick(self, tick: TradeTick) -> None:
        """
        Actions to be performed when the strategy is running and receives a trade tick.
        """
        pass

    def on_bar(self, bar: Bar) -> None:
        """
        Actions to be performed when the strategy is running and receives a bar.

        This method demonstrates the power of FactorExp by using multiple
        complex expressions to make trading decisions.
        """
        # Check if all indicators are initialized
        if not self.indicators_initialized():
            self.log.info(
                f"Waiting for FactorExp indicators to warm up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.BLUE,
            )
            return

        # Get current indicator values
        current_ema_ratio = self.ema_ratio.value
        current_volatility = self.volatility.value
        current_momentum = self.momentum.value
        current_trend_strength = self.trend_strength.value

        # Log indicator values for debugging
        self.log.info(
            f"Bar {self.cache.bar_count(self.config.bar_type)}: "
            f"EMA_Ratio={current_ema_ratio:.6f}, "
            f"Volatility={current_volatility:.6f}, "
            f"Momentum={current_momentum:.6f}, "
            f"Trend_Strength={current_trend_strength:.6f}",
            color=LogColor.CYAN,
        )

        # Only trade if volatility is above threshold (avoid choppy markets)
        if current_volatility < self.config.volatility_threshold:
            self.log.info(
                f"Volatility too low ({current_volatility:.6f} < {self.config.volatility_threshold}), skipping signals",
                color=LogColor.YELLOW,
            )
            self.prev_ema_ratio = current_ema_ratio
            return

        # Detect EMA crossovers
        if self.prev_ema_ratio is not None:
            # Bullish cross: fast EMA crosses above slow EMA (ratio goes above 1.0)
            bullish_cross = (self.prev_ema_ratio <= 1.0 and current_ema_ratio > 1.0)
            
            # Bearish cross: fast EMA crosses below slow EMA (ratio goes below 1.0)
            bearish_cross = (self.prev_ema_ratio >= 1.0 and current_ema_ratio < 1.0)

            if self.portfolio.is_flat(self.config.instrument_id):
                if bullish_cross and current_momentum > 0:
                    self.log.info(
                        f"BULLISH CROSS detected! EMA ratio: {self.prev_ema_ratio:.6f} -> {current_ema_ratio:.6f}, "
                        f"Momentum: {current_momentum:.6f}",
                        color=LogColor.GREEN,
                    )
                    self.entry_buy()
                elif bearish_cross and current_momentum < 0:
                    self.log.info(
                        f"BEARISH CROSS detected! EMA ratio: {self.prev_ema_ratio:.6f} -> {current_ema_ratio:.6f}, "
                        f"Momentum: {current_momentum:.6f}",
                        color=LogColor.RED,
                    )
                    self.entry_sell()
            else:
                # Check for exit conditions based on trend strength
                if self.portfolio.is_net_long(self.config.instrument_id) and current_trend_strength < -0.01:
                    self.log.info(
                        f"LONG EXIT: Trend strength weakening ({current_trend_strength:.6f})",
                        color=LogColor.YELLOW,
                    )
                    self.close_all_positions(self.config.instrument_id)
                elif self.portfolio.is_net_short(self.config.instrument_id) and current_trend_strength > 0.01:
                    self.log.info(
                        f"SHORT EXIT: Trend strength weakening ({current_trend_strength:.6f})",
                        color=LogColor.YELLOW,
                    )
                    self.close_all_positions(self.config.instrument_id)

        # Store current ratio for next iteration
        self.prev_ema_ratio = current_ema_ratio

    def entry_buy(self) -> None:
        """
        Enter a long position using FactorExp market conditions.
        """
        if not self.instrument:
            self.log.error("No instrument loaded")
            return

        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(self.config.trade_size),
        )

        self.submit_order(order)
        self.position_entry_bar = self.cache.bar_count(self.config.bar_type)

    def entry_sell(self) -> None:
        """
        Enter a short position using FactorExp market conditions.
        """
        if not self.instrument:
            self.log.error("No instrument loaded")
            return

        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(self.config.trade_size),
        )

        self.submit_order(order)
        self.position_entry_bar = self.cache.bar_count(self.config.bar_type)

    def on_data(self, data: Data) -> None:
        """
        Actions to be performed when the strategy is running and receives data.
        """
        pass

    def on_event(self, event: Event) -> None:
        """
        Actions to be performed when the strategy is running and receives an event.
        """
        if isinstance(event, (PositionOpened, PositionChanged)):
            self.log.info(
                f"Position event: {event.position_id} - {event.side} {event.quantity}",
                color=LogColor.BLUE,
            )
        elif isinstance(event, PositionClosed):
            bars_held = self.cache.bar_count(self.config.bar_type) - (self.position_entry_bar or 0)
            self.log.info(
                f"Position closed: {event.position_id} after {bars_held} bars",
                color=LogColor.MAGENTA,
            )

    def on_save(self) -> dict[str, bytes]:
        """
        Actions to be performed when the strategy is saved.
        """
        return {}

    def on_load(self, state: dict[str, bytes]) -> None:
        """
        Actions to be performed when the strategy is loaded.
        """
        pass

    def on_dispose(self) -> None:
        """
        Actions to be performed when the strategy is disposed.
        """
        pass