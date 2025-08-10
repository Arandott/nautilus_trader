"""
Example momentum strategy using FactorExp indicators.

This strategy demonstrates the integration of complex FactorExp expressions
within a Nautilus Trader strategy, showing the complete flow from market data
to trading signals.
"""

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy

from nautilus_trader.indicators.factorexp import FactorExpIndicator


class FactorExpMomentumConfig(StrategyConfig):
    """Configuration for the FactorExp momentum strategy."""
    
    bar_type: str = "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"
    position_size: float = 0.01
    entry_threshold: float = 0.5
    exit_threshold: float = -0.2
    
    # Complex factor expression combining multiple indicators
    factor_expression: str = """
        (TS_Mean($close, 20) / TS_Mean($close, 50) - 1) * 100
        + Log(TS_Std($close, 20) / TS_Std($close, 50))
        * Sign(TS_Delta($close, 5))
    """
    
    # Alternative expressions for testing
    sharpe_expression: str = "TS_Mean(TS_Delta($close, 1), 20) / TS_Std(TS_Delta($close, 1), 20)"
    volume_weighted_price: str = "TS_Sum($close * $volume, 10) / TS_Sum($volume, 10)"


class FactorExpMomentumStrategy(Strategy):
    """
    A momentum strategy using complex FactorExp expressions.
    
    This strategy demonstrates:
    1. Multiple rolling window operations with different periods
    2. Mathematical operations (division, logarithm, multiplication)
    3. Conditional logic using Sign function
    4. Complete integration with Nautilus Trader's event system
    """
    
    def __init__(self, config: FactorExpMomentumConfig):
        super().__init__(config)
        
        # Configuration
        self.bar_type_str = config.bar_type
        self.position_size = config.position_size
        self.entry_threshold = config.entry_threshold
        self.exit_threshold = config.exit_threshold
        self.factor_expression = config.factor_expression
        
        # State
        self.bar_type = None
        self.instrument = None
        self.in_position = False
        
        # Indicators (will be initialized in on_start)
        self.momentum_factor = None
        self.sharpe_factor = None
        self.vwap_factor = None
    
    def on_start(self):
        """Called when the strategy starts."""
        self.log.info("Strategy starting...")
        
        # Parse bar type
        self.bar_type = BarType.from_str(self.bar_type_str)
        
        # Get instrument
        self.instrument = self.cache.instrument(self.bar_type.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.bar_type.instrument_id}")
            self.stop()
            return
        
        # Create main momentum factor indicator
        self.momentum_factor = FactorExpIndicator(
            expression=self.factor_expression,
            period=50,  # Maximum period needed
            name="MomentumFactor"
        )
        
        # Create Sharpe ratio approximation indicator
        self.sharpe_factor = FactorExpIndicator(
            expression="TS_Mean(TS_Delta($close, 1), 20) / TS_Std(TS_Delta($close, 1), 20)",
            period=21,  # 20 + 1 for delta
            name="SharpeFactor"
        )
        
        # Create VWAP indicator
        self.vwap_factor = FactorExpIndicator(
            expression="TS_Sum($close * $volume, 10) / TS_Sum($volume, 10)",
            period=10,
            name="VWAPFactor"
        )
        
        # Register indicators
        self.register_indicator_for_bars(self.bar_type, self.momentum_factor)
        self.register_indicator_for_bars(self.bar_type, self.sharpe_factor)
        self.register_indicator_for_bars(self.bar_type, self.vwap_factor)
        
        # Subscribe to bars
        self.subscribe_bars(self.bar_type)
        
        self.log.info("Strategy initialized with complex factor expressions")
    
    def on_bar(self, bar: Bar):
        """
        Called when a new bar is received.
        
        This is where the complete call stack begins:
        1. Market data arrives as Bar object
        2. Bar is passed to registered indicators
        3. Indicators compute new values
        4. Strategy logic evaluates signals
        5. Orders are generated if conditions are met
        """
        self.log.debug(f"Received bar: {bar}")
        
        # Check if indicators are initialized
        if not self.momentum_factor.initialized:
            self.log.debug("Momentum factor not yet initialized")
            return
        
        # Get current factor values
        momentum_signal = self.momentum_factor.value
        sharpe_signal = self.sharpe_factor.value if self.sharpe_factor.initialized else 0.0
        vwap_signal = self.vwap_factor.value if self.vwap_factor.initialized else 0.0
        
        # Log signals for debugging
        self.log.info(
            f"Signals - Momentum: {momentum_signal:.4f}, "
            f"Sharpe: {sharpe_signal:.4f}, VWAP: {vwap_signal:.4f}"
        )
        
        # Trading logic
        if not self.in_position:
            # Entry logic: momentum above threshold and positive Sharpe
            if momentum_signal > self.entry_threshold and sharpe_signal > 0:
                self._enter_long(bar)
        else:
            # Exit logic: momentum below threshold or negative Sharpe
            if momentum_signal < self.exit_threshold or sharpe_signal < -0.5:
                self._exit_position(bar)
    
    def _enter_long(self, bar: Bar):
        """Enter a long position."""
        if self.in_position:
            return
        
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(self.position_size),
        )
        
        self.submit_order(order)
        self.in_position = True
        
        self.log.info(
            f"Entering long position at {bar.close} "
            f"(momentum={self.momentum_factor.value:.4f})"
        )
    
    def _exit_position(self, bar: Bar):
        """Exit the current position."""
        if not self.in_position:
            return
        
        order = self.order_factory.market(
            instrument_id=self.instrument.id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(self.position_size),
        )
        
        self.submit_order(order)
        self.in_position = False
        
        self.log.info(
            f"Exiting position at {bar.close} "
            f"(momentum={self.momentum_factor.value:.4f})"
        )
    
    def on_stop(self):
        """Called when the strategy stops."""
        # Close any open positions
        if self.in_position:
            self.log.warning("Strategy stopping with open position")
        
        self.log.info("Strategy stopped")
    
    def on_reset(self):
        """Called when the strategy is reset."""
        self.in_position = False
        self.log.info("Strategy reset")