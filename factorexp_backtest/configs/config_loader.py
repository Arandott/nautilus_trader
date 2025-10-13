"""
Configuration loader for factor-based trading strategies.

This module loads and validates factor configurations from YAML files,
providing standardized factor expressions for backtesting.

PHASE C EXTENSION: Now supports multi-instrument×factor batch backtesting.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class InstrumentConfig:
    """
    Configuration for a trading instrument.

    Parameters
    ----------
    instrument_id : str
        Instrument identifier (e.g., "BTCUSDT")
    venue : str
        Venue name (e.g., "BINANCE")
    bar_spec : str
        Bar specification (e.g., "15-MINUTE-LAST-EXTERNAL")
    base_currency : str
        Base currency code (e.g., "BTC")
    quote_currency : str
        Quote currency code (e.g., "USDT")
    data_source : str
        Data source type: "catalog" or "feather"
    """

    instrument_id: str
    venue: str
    bar_spec: str
    base_currency: str
    quote_currency: str
    data_source: str = "catalog"

    def __post_init__(self):
        """Validate instrument configuration."""
        if self.data_source not in ("catalog", "feather"):
            raise ValueError(
                f"data_source must be 'catalog' or 'feather', got {self.data_source}"
            )


@dataclass
class FactorConfig:
    """Configuration for a single factor."""

    factor_id: str  # NEW: Add factor ID for reference
    name: str
    expression: str
    description: str
    requires_extended: bool = False

    def __post_init__(self):
        """Validate factor configuration."""
        # Check if expression contains required Clip(ZScore(...)) pattern
        if not self._is_valid_expression(self.expression):
            raise ValueError(
                f"Factor expression must use Clip(ZScore(...)) pattern, got {self.expression}"
            )

    @staticmethod
    def _is_valid_expression(expression: str) -> bool:
        """Check if expression follows the standard pattern."""
        return "Clip" in expression and "ZScore" in expression


@dataclass
class RunConfig:
    """
    Configuration for a single backtest run (instrument×factor combination).

    Parameters
    ----------
    run_id : str
        Unique run identifier (e.g., "btc_amt_momentum")
    instrument : InstrumentConfig
        Instrument configuration
    factor : FactorConfig
        Factor configuration
    enabled : bool
        Whether this run is enabled for batch execution
    position_scale : float
        Position size scaling factor (default: 1.0)
    rebalance_interval : int | None
        Override for default rebalance interval (None = use default)
    """

    run_id: str
    instrument: InstrumentConfig
    factor: FactorConfig
    enabled: bool = True
    position_scale: float = 1.0
    rebalance_interval: int | None = None


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


class BacktestConfigLoader:
    """
    Loads and manages backtest configurations (Phase C).

    Supports:
    - Multiple instruments
    - Multiple factors
    - Instrument×factor run combinations
    - Backward compatibility with legacy single-factor configs
    """

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
        self.instruments: dict[str, InstrumentConfig] = {}
        self.factors: dict[str, FactorConfig] = {}
        self.runs: dict[str, RunConfig] = {}
        self.risk_config: RiskConfig | None = None
        self.execution_config: ExecutionConfig | None = None

        self._load_config()
        self._parse_instruments()
        self._parse_factors()
        self._parse_runs()
        self._parse_risk_config()
        self._parse_execution_config()

    def _load_config(self):
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            self.config_data = yaml.safe_load(f) or {}  # Handle empty files

    def _parse_instruments(self):
        """Parse instrument configurations (Phase C)."""
        instruments_data = self.config_data.get("instruments", {})

        for instrument_id, inst_data in instruments_data.items():
            self.instruments[instrument_id] = InstrumentConfig(
                instrument_id=instrument_id,
                venue=inst_data["venue"],
                bar_spec=inst_data["bar_spec"],
                base_currency=inst_data["base_currency"],
                quote_currency=inst_data["quote_currency"],
                data_source=inst_data.get("data_source", "catalog"),
            )

    def _parse_factors(self):
        """Parse factor configurations."""
        factors_data = self.config_data.get("factors", {})

        for factor_id, factor_data in factors_data.items():
            self.factors[factor_id] = FactorConfig(
                factor_id=factor_id,  # NEW: Store factor ID
                name=factor_data["name"],
                expression=factor_data["expression"],
                description=factor_data["description"],
                requires_extended=factor_data.get("requires_extended", False)
            )

    def _parse_runs(self):
        """Parse run configurations (Phase C)."""
        runs_data = self.config_data.get("runs", {})

        for run_id, run_data in runs_data.items():
            # Get instrument and factor
            instrument_id = run_data["instrument"]
            factor_id = run_data["factor"]

            if instrument_id not in self.instruments:
                raise ValueError(
                    f"Run '{run_id}' references unknown instrument '{instrument_id}'"
                )

            if factor_id not in self.factors:
                raise ValueError(
                    f"Run '{run_id}' references unknown factor '{factor_id}'"
                )

            instrument = self.instruments[instrument_id]
            factor = self.factors[factor_id]

            self.runs[run_id] = RunConfig(
                run_id=run_id,
                instrument=instrument,
                factor=factor,
                enabled=run_data.get("enabled", True),
                position_scale=run_data.get("position_scale", 1.0),
                rebalance_interval=run_data.get("rebalance_interval"),
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

    def iter_runs(self, run_ids: list[str] | None = None, enabled_only: bool = True) -> Iterator[RunConfig]:
        """
        Iterate over selected runs.

        Parameters
        ----------
        run_ids : list[str] | None
            Specific run IDs to iterate over. If None, uses all runs.
        enabled_only : bool
            If True, only yield enabled runs (default: True).

        Yields
        ------
        RunConfig
            Run configuration.
        """
        if run_ids is None:
            # Use all runs
            run_ids_to_process = list(self.runs.keys())
        else:
            # Validate provided run IDs
            for run_id in run_ids:
                if run_id not in self.runs:
                    raise KeyError(f"Run '{run_id}' not found in configuration")
            run_ids_to_process = run_ids

        # Yield runs
        for run_id in run_ids_to_process:
            run = self.runs[run_id]
            if not enabled_only or run.enabled:
                yield run

    def list_runs(self, enabled_only: bool = True) -> list[str]:
        """
        Get list of run IDs.

        Parameters
        ----------
        enabled_only : bool
            If True, only return enabled runs (default: True).

        Returns
        -------
        list[str]
            List of run IDs.
        """
        if enabled_only:
            return [run_id for run_id, run in self.runs.items() if run.enabled]
        else:
            return list(self.runs.keys())

    def get_run(self, run_id: str) -> RunConfig:
        """
        Get a run configuration by ID.

        Parameters
        ----------
        run_id : str
            The run identifier.

        Returns
        -------
        RunConfig
            The run configuration.

        Raises
        ------
        KeyError
            If run_id not found.
        """
        if run_id not in self.runs:
            raise KeyError(f"Run '{run_id}' not found")
        return self.runs[run_id]


# Backward compatibility alias
FactorConfigLoader = BacktestConfigLoader
