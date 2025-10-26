"""
Official Nautilus Trader StrategyConfig for FactorExp live trading.

This configuration follows Nautilus Trader official patterns for maintainability,
framework compatibility, and future-proofing.
"""

from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


class FactorExpLiveStrategyConfig(StrategyConfig, frozen=True):
    """
    Official Nautilus Trader configuration for the FactorExp live trading strategy.

    Live trading now consumes the exact same factor catalog used by the backtest
    (Clip(ZScore(...)) expressions loaded from YAML). The configuration exposes
    the factor selection and optional overrides while keeping the capital and
    risk controls which are still strategy-specific.

    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument ID for the strategy.
    bar_type : BarType
        The bar type for the strategy (e.g., 15-MINUTE-LAST-INTERNAL).
    factor_config_path : str, default "../factorexp_backtest/configs/factors.yaml"
        Path to the shared factor definition YAML.
    factor_id : str, default "vwap_return_std"
        Factor identifier to load from the YAML file.
    zscore_period : PositiveInt, default 5760
        Rolling window used by the FactorExp Clip(ZScore(...)) expression.
    clip_min : float, default -2.0
        Minimum clip bound applied to the factor output.
    clip_max : float, default 2.0
        Maximum clip bound applied to the factor output.
    min_signal_magnitude : PositiveFloat, default 0.05
        Absolute factor magnitude required before generating a trading signal
        (prevents noise around zero).
    max_account_usage_pct : PositiveFloat, default 0.8
        Maximum percentage of account equity to use (80%).
    max_absolute_exposure : PositiveFloat, default 5000.0
        Maximum trading capital to allocate in USD (set via ACCOUNT_SIZE_USD env var).
    position_risk_pct : PositiveFloat, default 0.02
        Risk percentage per position (2%).
    stop_loss_pct : PositiveFloat, default 0.015
        Stop loss percentage (1.5%).
    take_profit_pct : PositiveFloat, default 0.03
        Take profit percentage (3%).
    use_market_orders : bool, default True
        Whether to use market orders (True) or limit orders (False).
    max_daily_trades : PositiveInt, default 20
        Maximum number of daily trades.
    max_daily_loss_usd : PositiveFloat, default 200.0
        Maximum daily loss in USD.
    max_drawdown_pct : PositiveFloat, default 0.05
        Maximum drawdown percentage (5%).
    """

    # Required parameters
    instrument_id: InstrumentId
    bar_type: BarType

    # Shared factor configuration
    factor_config_path: str = "../factorexp_backtest/configs/factors.yaml"
    factor_id: str = "vwap_return_std"
    zscore_period: PositiveInt = 5760
    clip_min: float = -2.0
    clip_max: float = 2.0
    min_signal_magnitude: PositiveFloat = 0.05

    # Professional capital management
    max_account_usage_pct: PositiveFloat = 0.8
    max_absolute_exposure: PositiveFloat = 5000.0
    position_risk_pct: PositiveFloat = 0.02

    # Risk management parameters
    stop_loss_pct: PositiveFloat = 0.015
    take_profit_pct: PositiveFloat = 0.03

    # Trading parameters
    use_market_orders: bool = True

    # Daily limits and risk controls
    max_daily_trades: PositiveInt = 20
    max_daily_loss_usd: PositiveFloat = 200.0
    max_drawdown_pct: PositiveFloat = 0.05

    @classmethod
    def create_small_account_config(
        cls,
        instrument_id: InstrumentId,
        bar_type: BarType,
        account_size_usd: float = 200.0,
        **kwargs
    ) -> "FactorExpLiveStrategyConfig":
        """
        Create optimized configuration for small accounts (≤$500).
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Trading instrument
        bar_type : BarType  
            Bar type for data feeds
        account_size_usd : float, default 200.0
            Account size in USD for optimization
        **kwargs
            Override any other configuration parameters
            
        Returns
        -------
        FactorExpLiveStrategyConfig
            Optimized configuration for small accounts
        """
        # Conservative parameters for small accounts
        conservative_config = {
            # Reduced capital usage for safety margin
            "max_account_usage_pct": 0.6,  # 60% instead of 80%

            # Lower position risk to account for minimum trade sizes
            "position_risk_pct": 0.015,  # 1.5% instead of 2%

            # Tighter stop loss for small accounts
            "stop_loss_pct": 0.012,  # 1.2% instead of 1.5%

            # Conservative take profit
            "take_profit_pct": 0.025,  # 2.5% instead of 3%

            # Reduced daily limits proportional to account size
            "max_daily_trades": 10,  # Fewer trades for small accounts
            "max_daily_loss_usd": account_size_usd * 0.05,  # 5% of account

            # Tighter drawdown control
            "max_drawdown_pct": 0.03,  # 3% instead of 5%

            # Conservative absolute exposure (should not be reached for small accounts)
            "max_absolute_exposure": max(account_size_usd * 2, 500.0),

            # Require a slightly higher factor magnitude to trade very small accounts
            "min_signal_magnitude": 0.1,
        }

        # Merge with any user overrides
        conservative_config.update(kwargs)

        return cls(
            instrument_id=instrument_id,
            bar_type=bar_type,
            **conservative_config
        )


# Deprecated - for backward compatibility only
# Will be removed in future versions
class FactorExpConfig:
    """
    DEPRECATED: Legacy configuration class.
    
    Use FactorExpLiveStrategyConfig instead for new implementations.
    This class is maintained for backward compatibility only.
    """

    def __init__(self):
        import warnings
        warnings.warn(
            "FactorExpConfig is deprecated. Use FactorExpLiveStrategyConfig instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Legacy default values for backward compatibility
        self.instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
        self.primary_instrument = "BTCUSDT-PERP.BINANCE"
        self.max_account_usage_pct = 0.8
        self.max_absolute_exposure = 5000.0
        self.position_risk_pct = 0.02
        self.commission_rate = 0.0004
        self.stop_loss_pct = 0.015
        self.take_profit_pct = 0.03
        self.volatility_threshold = 0.001
        self.max_daily_trades = 20
        self.max_daily_loss_usd = 200.0
        self.max_drawdown_pct = 0.05
