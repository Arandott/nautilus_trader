"""
Official Nautilus Trader StrategyConfig for FactorExp live trading.

This configuration follows Nautilus Trader official patterns for maintainability,
framework compatibility, and future-proofing.
"""

from typing import Tuple

from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import root_validator


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
        Factor identifier to load from the YAML file (used when `factor_ids` 未指定).
    factor_ids : Sequence[str] | None, default None
        多因子交易时加载的因子 ID 列表；若提供，则会覆盖 `factor_id` 并按顺序加载。
    zscore_period : PositiveInt, default 5760
        Rolling window used by the FactorExp Clip(ZScore(...)) expression.
    clip_min : float, default -2.0
        Minimum clip bound applied to the factor output.
    clip_max : float, default 2.0
        Maximum clip bound applied to the factor output.
    min_signal_magnitude : PositiveFloat, default 0.05
        Absolute factor magnitude required before generating a trading signal
        (prevents noise around zero).
    max_account_usage_pct : PositiveFloat, default 0.2
        Maximum percentage of account equity to treat as available margin (80%).
    max_absolute_exposure : PositiveFloat, default 5000.0
        Legacy alias for maximum margin allocation in USD; used when capital_allocation_usd is omitted.
    capital_allocation_usd : PositiveFloat | None, default None
        Explicit margin budget (pre-leverage) for live trading. When omitted, falls back to max_absolute_exposure.
    target_notional_usd : PositiveFloat | None, default None
        Optional target notional exposure after leverage. If omitted, it is derived from margin × leverage.
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
    factor_ids: Tuple[str, ...] | None = None
    zscore_period: PositiveInt = 5760
    clip_min: float = -2.0
    clip_max: float = 2.0
    min_signal_magnitude: PositiveFloat = 0.05

    # Professional capital management
    max_account_usage_pct: PositiveFloat = 0.2
    max_absolute_exposure: PositiveFloat = 5000.0
    capital_allocation_usd: PositiveFloat | None = None
    target_notional_usd: PositiveFloat | None = None
    max_leverage: PositiveFloat | None = None
    position_risk_pct: PositiveFloat = 0.02  # todo: strategy未消费

    # Risk management parameters
    stop_loss_pct: PositiveFloat = 0.015  # todo: 仅在无风险配置时 fallback
    take_profit_pct: PositiveFloat = 0.03  # todo: 尚未接入执行逻辑

    # Trading parameters
    use_market_orders: bool = True  # todo: 策略始终使用市价单，未读此配置

    # Daily limits and risk controls
    max_daily_trades: PositiveInt = 20  # todo: 未接入风险监控
    max_daily_loss_usd: PositiveFloat = 200.0  # todo: 未接入风险监控
    max_drawdown_pct: PositiveFloat = 0.05  # todo: 未接入风险监控

    @root_validator(pre=True)
    def _normalize_factor_ids(cls, values: dict) -> dict:
        """
        Ensure factor_ids is normalized and consistent with legacy factor_id.
        """
        if values is None:
            return {}
        if isinstance(values, cls):
            return values
        if not isinstance(values, dict):
            return dict(values)

        factor_ids = values.get("factor_ids")
        factor_id = values.get("factor_id")

        if factor_ids is None or factor_ids == []:
            # 默认使用单因子配置
            if factor_id is None:
                raise ValueError("factor_id or factor_ids must be provided")
            values["factor_ids"] = (factor_id,)
            return values

        # factor_ids 提供时，兼容字符串或可迭代形式
        if isinstance(factor_ids, str):
            parts = [part.strip() for part in factor_ids.split(",")]
        else:
            parts = [str(part).strip() for part in factor_ids]

        normalized = tuple(part for part in parts if part)
        if not normalized:
            raise ValueError("factor_ids must contain at least one non-empty ID")

        # 同步 legacy 字段
        values["factor_ids"] = normalized
        values["factor_id"] = normalized[0]
        return values

    @root_validator(skip_on_failure=True)
    def _validate_capital_parameters(cls, values: dict) -> dict:
        if values is None:
            return {}
        if isinstance(values, cls):
            return values
        if not isinstance(values, dict):
            return dict(values)

        capital = values.get("capital_allocation_usd")
        max_abs = values.get("max_absolute_exposure")
        target_notional = values.get("target_notional_usd")
        max_leverage = values.get("max_leverage")

        if capital is not None and capital <= 0:
            raise ValueError("capital_allocation_usd must be positive when provided")
        if max_abs is not None and max_abs <= 0:
            raise ValueError("max_absolute_exposure must be positive")
        if target_notional is not None and target_notional <= 0:
            raise ValueError("target_notional_usd must be positive when provided")
        if max_leverage is not None and max_leverage <= 0:
            raise ValueError("max_leverage must be positive when provided")

        return values

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

        # Capital allocation defaults to configured usage of the declared account size
        capital_allocation = account_size_usd * conservative_config["max_account_usage_pct"]
        max_absolute = float(conservative_config.get("max_absolute_exposure", 0.0))
        if max_absolute > 0:
            capital_allocation = min(capital_allocation, max_absolute)
        conservative_config["capital_allocation_usd"] = capital_allocation

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
        self.max_account_usage_pct = 0.2
        self.max_absolute_exposure = 5000.0
        self.capital_allocation_usd = 5000.0
        self.position_risk_pct = 0.02
        self.commission_rate = 0.0004
        self.stop_loss_pct = 0.015
        self.take_profit_pct = 0.03
        self.volatility_threshold = 0.001
        self.max_daily_trades = 20
        self.max_daily_loss_usd = 200.0
        self.max_drawdown_pct = 0.05
