"""Configuration management for factor backtesting (Phase C: Multi-instrument×factor support)."""

from .config_loader import BacktestConfigLoader
from .config_loader import ExecutionConfig
from .config_loader import FactorConfig
from .config_loader import FactorConfigLoader
from .config_loader import InstrumentConfig
from .config_loader import RiskConfig
from .config_loader import RunConfig


__all__ = [
    # New Phase C classes
    "BacktestConfigLoader",
    "InstrumentConfig",
    "RunConfig",
    # Original classes (backward compatibility)
    "ExecutionConfig",
    "FactorConfig",
    "FactorConfigLoader",
    "RiskConfig",
]
