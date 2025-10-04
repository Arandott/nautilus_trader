"""
Configuration loader for factor-based trading strategies.

This module loads and validates factor configurations from YAML files,
providing standardized factor expressions for backtesting.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FactorConfig:
    """Configuration for a single factor."""

    name: str
    expression: str
    description: str
    requires_extended: bool = False

    def __post_init__(self):
        """Validate factor configuration."""
        # Check if expression contains required Clip(Zscore(...)) pattern
        if not self._is_valid_expression(self.expression):
            raise ValueError(
                f"Factor expression must use Clip(Zscore(...)) pattern, got {self.expression}"
            )

    @staticmethod
    def _is_valid_expression(expression: str) -> bool:
        """Check if expression follows the standard pattern."""
        return "Clip" in expression and "Zscore" in expression


@dataclass
class RiskConfig:
    """Risk management configuration."""

    max_position_size: float
    stop_loss: float
    min_rebalance_interval: int
    max_rebalance_interval: int


@dataclass
class ExecutionConfig:
    """Execution configuration."""

    slippage_bps: int
    commission_bps: int
    min_order_size: float
    max_order_size: float


class FactorConfigLoader:
    """Loads and manages factor configurations."""

    def __init__(self, config_path: Path):
        """
        Initialize the config loader.

        Parameters
        ----------
        config_path : Path
            Path to the YAML configuration file.
        """
        self.config_path = config_path
        self.config_data: dict[str, Any] = {}
        self.factors: dict[str, FactorConfig] = {}
        self.risk_config: RiskConfig | None = None
        self.execution_config: ExecutionConfig | None = None

        self._load_config()
        self._parse_factors()
        self._parse_risk_config()
        self._parse_execution_config()

    def _load_config(self):
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            self.config_data = yaml.safe_load(f)

    def _parse_factors(self):
        """Parse factor configurations."""
        factors_data = self.config_data.get("factors", {})

        for factor_id, factor_data in factors_data.items():
            self.factors[factor_id] = FactorConfig(
                name=factor_data["name"],
                expression=factor_data["expression"],
                description=factor_data["description"],
                requires_extended=factor_data.get("requires_extended", False)
            )

    def _parse_risk_config(self):
        """Parse risk management configuration."""
        risk_data = self.config_data.get("risk_management", {})

        if risk_data:
            self.risk_config = RiskConfig(
                max_position_size=risk_data["max_position_size"],
                stop_loss=risk_data["stop_loss"],
                min_rebalance_interval=risk_data["min_rebalance_interval"],
                max_rebalance_interval=risk_data["max_rebalance_interval"]
            )

    def _parse_execution_config(self):
        """Parse execution configuration."""
        exec_data = self.config_data.get("execution", {})

        if exec_data:
            self.execution_config = ExecutionConfig(
                slippage_bps=exec_data["slippage_bps"],
                commission_bps=exec_data["commission_bps"],
                min_order_size=exec_data["min_order_size"],
                max_order_size=exec_data["max_order_size"]
            )

    def get_factor(self, factor_id: str) -> FactorConfig:
        """
        Get a factor configuration by ID.

        Parameters
        ----------
        factor_id : str
            The factor identifier.

        Returns
        -------
        FactorConfig
            The factor configuration.
        """
        if factor_id not in self.factors:
            raise KeyError(f"Factor '{factor_id}' not found")
        return self.factors[factor_id]

    def list_factors(self) -> list[str]:
        """
        Get list of available factor IDs.

        Returns
        -------
        List[str]
            List of factor identifiers.
        """
        return list(self.factors.keys())

    def validate_extended_support(self, has_extended: bool) -> list[str]:
        """
        Get factors that can run with current extended bar support.

        Parameters
        ----------
        has_extended : bool
            Whether extended bar support is available.

        Returns
        -------
        List[str]
            List of factor IDs that can run.
        """
        if has_extended:
            return list(self.factors.keys())
        else:
            # Only return factors that don't require extended fields
            return [fid for fid, factor in self.factors.items()
                    if not factor.requires_extended]

    def get_defaults(self) -> dict[str, Any]:
        """
        Get default configuration values.

        Returns
        -------
        Dict[str, Any]
            Default configuration values.
        """
        return self.config_data.get("defaults", {})
