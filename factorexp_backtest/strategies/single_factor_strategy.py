"""
Single-factor trading strategy for backtesting.

This strategy runs ONE factor at a time, where the factor output
directly maps to position sizing under 2x leverage.
"""

from decimal import Decimal
from pathlib import Path

from factorexp_backtest.configs.config_loader import FactorConfigLoader
from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy


class SingleFactorStrategyConfig(StrategyConfig):
    """
    Configuration for SingleFactorStrategy.

    Parameters
    ----------
    instrument_id : str
        The instrument ID for trading.
    bar_type : str
        The bar type specification for data.
    config_path : str
        Path to the factor configuration YAML file.
    factor_id : str
        The single factor ID to run (e.g., "amt_momentum").
    rebalance_interval : int, optional
        Bars between rebalances (default from config or 30).
    position_scale : float
        Scale factor for position sizing (1.0 = use factor value directly).
    """

    instrument_id: str
    bar_type: str = "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
    config_path: str = "configs/factors.yaml"
    factor_id: str = "amt_momentum"
    rebalance_interval: int | None = None
    position_scale: float = 1.0


class SingleFactorStrategy(Strategy):
    """
    A single-factor trading strategy.

    This strategy runs ONE factor where the output Clip(ZScore(...), -2, 2)
    directly maps to position sizing under 2x leverage.
    """

    def __init__(self, config: SingleFactorStrategyConfig):
        """Initialize the strategy."""
        super().__init__(config)

        # Configuration
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        # Convert bar_type string to BarType object - 以复用现有为荣
        self.bar_type = BarType.from_str(config.bar_type)
        self.factor_id = config.factor_id
        self.position_scale = Decimal(str(config.position_scale))

        # Load configuration
        config_path = Path(config.config_path)
        if not config_path.is_absolute():
            # Make path relative to factorexp_backtest directory
            config_path = Path(__file__).parent.parent / config_path

        self.config_loader = FactorConfigLoader(config_path)
        self.factor_config = self.config_loader.get_factor(config.factor_id)
        self.risk_config = self.config_loader.risk_config
        self.execution_config = self.config_loader.execution_config

        # Get defaults
        defaults = self.config_loader.get_defaults()
        self.zscore_period = defaults.get("zscore_period", 5760)

        # State
        self.instrument: Instrument | None = None
        self.factor_indicator: FactorExpIndicator | None = None
        self.current_position: float = 0.0

    def on_start(self):
        """Actions to be performed on strategy start."""
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument {self.instrument_id}")
            self.stop()  # Stop strategy gracefully - 以遵循规范为荣
            return

        # Check if factor requires extended bar support
        if self.factor_config.requires_extended:
            # Check support using feature flag approach - 以复用现有为荣
            try:
                from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
                has_extended = bool(EXTENDED_BAR_FIELD_SPECS)
            except Exception:
                has_extended = False

            if not has_extended:
                self.log.error(
                    f"Factor '{self.factor_config.name}' requires extended bar support "
                    f"which is not available"
                )
                self.stop()
                return

        # Initialize the single factor indicator
        self.factor_indicator = FactorExpIndicator(
            expression=self.factor_config.expression,
            period=self.zscore_period
        )

        # Register indicator for automatic updates - 以复用现有为荣
        self.register_indicator_for_bars(self.bar_type, self.factor_indicator)

        # Request historical data for warmup - CRITICAL!
        self.request_bars(self.bar_type)

        # Subscribe to live bar data
        self.subscribe_bars(self.bar_type)

        self.log.info(
            f"SingleFactorStrategy initialized with factor '{self.factor_config.name}'",
            LogColor.GREEN,
        )
        self.log.info(
            f"Expression: {self.factor_config.expression[:80]}...",
            LogColor.CYAN,
        )
        self.log.info(
            "Rebalance: Every bar (15min)",
            LogColor.CYAN,
        )

    def on_bar(self, bar: Bar):
        """
        Handle bar data update.

        Parameters
        ----------
        bar : Bar
            The bar received.
        """
        # Update factor indicator
        if self.factor_indicator:
            self.factor_indicator.handle_bar(bar)

        # Check if indicator is ready
        if not self.factor_indicator or not self.factor_indicator.initialized:
            self.log.debug("Factor indicator warming up...")
            return

        # Rebalance on EVERY bar (factor value → position mapping)
        self._rebalance_portfolio()


    def _rebalance_portfolio(self):
        """Rebalance portfolio based on the single factor signal."""
        # Get factor value (already Clip(ZScore(...), -2, 2))
        factor_value = self.factor_indicator.value

        # Validate factor value range
        if not -2 <= factor_value <= 2:
            self.log.error(f"Factor value {factor_value} outside expected range [-2, 2]")
            return

        # Apply position scale
        target_position = factor_value * float(self.position_scale)

        # Apply risk limits if configured
        if self.risk_config:
            max_size = self.risk_config.max_position_size
            target_position = max(-max_size, min(max_size, target_position))

        # Get current position - 以复用现有为荣
        positions = self.cache.positions_open(instrument_id=self.instrument_id)
        current_signed_qty = 0.0
        if positions:
            position = positions[0]
            current_signed_qty = float(position.signed_qty)

        self.log.info(
            f"Factor value: {factor_value:.4f}, "
            f"Target position: {target_position:.4f}, "
            f"Current position: {current_signed_qty:.4f}",
            LogColor.BLUE,
        )

        # Calculate position change needed
        position_delta = target_position - current_signed_qty

        # Apply execution limits
        if self.execution_config:
            min_order = self.execution_config.min_order_size
            if abs(position_delta) < min_order:
                self.log.debug(f"Position delta {position_delta:.4f} below minimum order size")
                return

        # Adjust position efficiently - 以复用现有为荣
        self._adjust_position(target_position, current_signed_qty)

    def _adjust_position(self, target: float, current: float):
        """
        Efficiently adjust position to target size.

        Parameters
        ----------
        target : float
            Target position size (signed).
        current : float
            Current position size (signed).
        """
        delta = target - current

        # Skip if delta is too small
        if abs(delta) < 0.001:
            return

        # Determine order side based on delta
        if delta > 0:
            order_side = OrderSide.BUY
        else:
            order_side = OrderSide.SELL

        # Convert delta to quantity
        quantity = self.instrument.make_qty(Decimal(str(abs(delta))))

        # Create market order for the delta
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=order_side,
            quantity=quantity,
        )

        self.submit_order(order)

        action = "Increasing" if delta > 0 else "Decreasing"
        self.log.info(
            f"{action} position by {abs(delta):.4f} to target {target:.4f}",
            LogColor.GREEN if delta > 0 else LogColor.RED,
        )

        # Update tracking
        self.current_position = target

    def on_stop(self):
        """Actions to be performed on strategy stop."""
        # Cancel all orders and close all positions - 以遵循规范为荣
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)

        # Unsubscribe from data
        self.unsubscribe_bars(self.bar_type)

        self.log.info("Strategy stopped", LogColor.RED)

    def on_reset(self):
        """Actions to be performed on strategy reset."""
        # Reset indicator
        if self.factor_indicator:
            self.factor_indicator.reset()

        # Reset state
        self.current_position = 0.0

        self.log.info("Strategy reset")
