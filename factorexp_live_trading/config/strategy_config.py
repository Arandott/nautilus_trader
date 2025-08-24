"""
Official Nautilus Trader StrategyConfig for FactorExp live trading.

This configuration follows Nautilus Trader official patterns for maintainability,
framework compatibility, and future-proofing.
"""

from nautilus_trader.config import PositiveFloat, PositiveInt, StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


class FactorExpLiveStrategyConfig(StrategyConfig, frozen=True):
    """
    Official Nautilus Trader configuration for FactorExp live trading strategy.
    
    Follows official StrategyConfig pattern for framework compatibility
    and maintainability. All parameters are validated using Nautilus types.
    
    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument ID for the strategy
    bar_type : BarType
        The bar type for the strategy (e.g., 1-MINUTE-LAST-EXTERNAL)
    ema_fast_period : PositiveInt, default 12
        Fast EMA period for trend detection
    ema_slow_period : PositiveInt, default 26
        Slow EMA period for trend detection
    volatility_period : PositiveInt, default 20
        Period for volatility calculation
    momentum_period : PositiveInt, default 14
        Period for momentum calculation
    max_account_usage_pct : PositiveFloat, default 0.8
        Maximum percentage of account equity to use (80%)
    max_absolute_exposure : PositiveFloat, default 5000.0
        Maximum trading capital to use in USD (set via ACCOUNT_SIZE_USD env var)
        This is the amount YOU want to allocate for trading, not your total account balance
    position_risk_pct : PositiveFloat, default 0.02
        Risk percentage per position (2%)
    stop_loss_pct : PositiveFloat, default 0.015
        Stop loss percentage (1.5%)
    take_profit_pct : PositiveFloat, default 0.03
        Take profit percentage (3%)
    volatility_threshold : PositiveFloat, default 0.001
        Minimum volatility threshold for trading
    ema_ratio_long_threshold : PositiveFloat, default 1.005
        EMA ratio threshold for long signals
    ema_ratio_short_threshold : PositiveFloat, default 0.995
        EMA ratio threshold for short signals
    momentum_threshold : PositiveFloat, default 0.001
        Momentum threshold for signal confirmation
    use_market_orders : bool, default True
        Whether to use market orders (True) or limit orders (False)
    max_daily_trades : PositiveInt, default 20
        Maximum number of daily trades
    max_daily_loss_usd : PositiveFloat, default 200.0
        Maximum daily loss in USD
    max_drawdown_pct : PositiveFloat, default 0.05
        Maximum drawdown percentage (5%)
    """
    
    # Required parameters
    instrument_id: InstrumentId
    bar_type: BarType
    
    # FactorExp indicator parameters
    ema_fast_period: PositiveInt = 12
    ema_slow_period: PositiveInt = 26
    volatility_period: PositiveInt = 20
    momentum_period: PositiveInt = 14
    
    # Professional capital management
    max_account_usage_pct: PositiveFloat = 0.8
    max_absolute_exposure: PositiveFloat = 5000.0
    position_risk_pct: PositiveFloat = 0.02
    
    # Risk management parameters
    stop_loss_pct: PositiveFloat = 0.015
    take_profit_pct: PositiveFloat = 0.03
    volatility_threshold: PositiveFloat = 0.001
    
    # Signal thresholds
    ema_ratio_long_threshold: PositiveFloat = 1.005
    ema_ratio_short_threshold: PositiveFloat = 0.995
    momentum_threshold: PositiveFloat = 0.001
    
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