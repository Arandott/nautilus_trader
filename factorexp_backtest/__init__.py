# FactorExp Backtesting Framework
"""
A backtesting framework for factor-based trading strategies using extended bar fields.

This framework supports additional market microstructure data beyond standard OHLCV,
such as amt (成交额), vwap, bid/ask volumes, etc.
"""

__version__ = "0.1.0"
__author__ = "Nautilus Trader Team"

from .loaders import FeatherBarLoader
from .strategies import SingleFactorStrategy, SingleFactorStrategyConfig
from .configs import FactorConfigLoader

__all__ = [
    "FeatherBarLoader",
    "SingleFactorStrategy",
    "SingleFactorStrategyConfig",
    "FactorConfigLoader",
]