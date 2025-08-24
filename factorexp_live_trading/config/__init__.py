# FactorExp Live Trading Configuration Module
# Import only what's needed to avoid dependency issues

# Lazy imports to prevent nautilus_trader dependency issues
def _get_trading_config():
    from .trading_config import TradingConfig, create_trading_node_config
    return TradingConfig, create_trading_node_config

def _get_strategy_config():
    from .strategy_config import FactorExpConfig
    return FactorExpConfig

# Always available imports
from .security import SecureConfigManager

__all__ = [
    "SecureConfigManager",
    "_get_trading_config",
    "_get_strategy_config"
]