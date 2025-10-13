"""
Unit tests for BacktestConfigLoader (Phase C).

Tests cover:
- Instrument configuration parsing
- Run configuration parsing
- Schema validation
- Backward compatibility
- Error handling
"""

import pytest
from pathlib import Path
from factorexp_backtest.configs import (
    BacktestConfigLoader,
    FactorConfigLoader,
    InstrumentConfig,
    RunConfig,
    FactorConfig,
)


@pytest.fixture
def config_path():
    """Path to test configuration file."""
    return Path(__file__).parent.parent / "configs" / "factors.yaml"


class TestInstrumentConfig:
    """Tests for InstrumentConfig dataclass."""

    def test_valid_instrument(self):
        """Test creating valid instrument configuration."""
        inst = InstrumentConfig(
            instrument_id="BTCUSDT",
            venue="BINANCE",
            bar_spec="15-MINUTE-LAST-EXTERNAL",
            base_currency="BTC",
            quote_currency="USDT",
            data_source="catalog",
        )
        assert inst.instrument_id == "BTCUSDT"
        assert inst.venue == "BINANCE"
        assert inst.data_source == "catalog"

    def test_invalid_data_source(self):
        """Test invalid data_source raises ValueError."""
        with pytest.raises(ValueError, match="data_source must be"):
            InstrumentConfig(
                instrument_id="BTCUSDT",
                venue="BINANCE",
                bar_spec="15-MINUTE-LAST-EXTERNAL",
                base_currency="BTC",
                quote_currency="USDT",
                data_source="invalid",
            )

    def test_default_data_source(self):
        """Test default data_source is 'catalog'."""
        inst = InstrumentConfig(
            instrument_id="BTCUSDT",
            venue="BINANCE",
            bar_spec="15-MINUTE-LAST-EXTERNAL",
            base_currency="BTC",
            quote_currency="USDT",
        )
        assert inst.data_source == "catalog"


class TestRunConfig:
    """Tests for RunConfig dataclass."""

    def test_valid_run(self):
        """Test creating valid run configuration."""
        inst = InstrumentConfig(
            instrument_id="BTCUSDT",
            venue="BINANCE",
            bar_spec="15-MINUTE-LAST-EXTERNAL",
            base_currency="BTC",
            quote_currency="USDT",
        )
        factor = FactorConfig(
            factor_id="amt_momentum",
            name="AMT Momentum",
            expression="Clip(ZScore($amt / TS_Mean($amt, 96), 5760), -2, 2)",
            description="Test factor",
        )
        run = RunConfig(
            run_id="btc_amt_momentum",
            instrument=inst,
            factor=factor,
            enabled=True,
            position_scale=1.0,
        )
        assert run.run_id == "btc_amt_momentum"
        assert run.instrument.instrument_id == "BTCUSDT"
        assert run.factor.factor_id == "amt_momentum"
        assert run.enabled is True
        assert run.position_scale == 1.0

    def test_default_values(self):
        """Test default values for RunConfig."""
        inst = InstrumentConfig(
            instrument_id="BTCUSDT",
            venue="BINANCE",
            bar_spec="15-MINUTE-LAST-EXTERNAL",
            base_currency="BTC",
            quote_currency="USDT",
        )
        factor = FactorConfig(
            factor_id="test",
            name="Test",
            expression="Clip(ZScore($close, 100), -2, 2)",
            description="Test",
        )
        run = RunConfig(run_id="test_run", instrument=inst, factor=factor)
        assert run.enabled is True
        assert run.position_scale == 1.0
        assert run.rebalance_interval is None


class TestBacktestConfigLoader:
    """Tests for BacktestConfigLoader."""

    def test_load_config(self, config_path):
        """Test loading configuration file."""
        loader = BacktestConfigLoader(config_path)
        assert loader.config_data is not None
        assert "defaults" in loader.config_data
        assert "factors" in loader.config_data
        assert "instruments" in loader.config_data
        assert "runs" in loader.config_data

    def test_parse_instruments(self, config_path):
        """Test parsing instruments from config."""
        loader = BacktestConfigLoader(config_path)
        assert len(loader.instruments) > 0
        assert "BTCUSDT" in loader.instruments

        btc = loader.instruments["BTCUSDT"]
        assert btc.venue == "BINANCE"
        assert btc.bar_spec == "15-MINUTE-LAST-EXTERNAL"
        assert btc.base_currency == "BTC"
        assert btc.quote_currency == "USDT"

    def test_parse_factors(self, config_path):
        """Test parsing factors from config."""
        loader = BacktestConfigLoader(config_path)
        assert len(loader.factors) > 0
        assert "amt_momentum" in loader.factors

        factor = loader.factors["amt_momentum"]
        assert factor.factor_id == "amt_momentum"
        assert factor.name == "AMT Momentum"
        assert "Clip" in factor.expression
        assert "ZScore" in factor.expression

    def test_parse_runs(self, config_path):
        """Test parsing runs from config."""
        loader = BacktestConfigLoader(config_path)
        assert len(loader.runs) > 0
        assert "btc_amt_momentum" in loader.runs

        run = loader.runs["btc_amt_momentum"]
        assert run.run_id == "btc_amt_momentum"
        assert run.instrument.instrument_id == "BTCUSDT"
        assert run.factor.factor_id == "amt_momentum"
        assert run.enabled is True

    def test_iter_runs_all(self, config_path):
        """Test iterating over all enabled runs."""
        loader = BacktestConfigLoader(config_path)
        runs = list(loader.iter_runs())
        assert len(runs) > 0

        # All returned runs should be enabled
        for run in runs:
            assert run.enabled is True

    def test_iter_runs_specific(self, config_path):
        """Test iterating over specific run IDs."""
        loader = BacktestConfigLoader(config_path)
        run_ids = ["btc_amt_momentum", "btc_price_momentum"]
        runs = list(loader.iter_runs(run_ids=run_ids))

        assert len(runs) == 2
        assert runs[0].run_id == "btc_amt_momentum"
        assert runs[1].run_id == "btc_price_momentum"

    def test_iter_runs_disabled(self, config_path):
        """Test iterating includes disabled runs when enabled_only=False."""
        loader = BacktestConfigLoader(config_path)

        # Get all runs including disabled
        all_runs = list(loader.iter_runs(enabled_only=False))
        enabled_runs = list(loader.iter_runs(enabled_only=True))

        assert len(all_runs) >= len(enabled_runs)

    def test_list_runs(self, config_path):
        """Test listing run IDs."""
        loader = BacktestConfigLoader(config_path)
        run_ids = loader.list_runs()

        assert len(run_ids) > 0
        assert "btc_amt_momentum" in run_ids
        assert all(isinstance(rid, str) for rid in run_ids)

    def test_get_run(self, config_path):
        """Test getting specific run by ID."""
        loader = BacktestConfigLoader(config_path)
        run = loader.get_run("btc_amt_momentum")

        assert run.run_id == "btc_amt_momentum"
        assert run.instrument.instrument_id == "BTCUSDT"

    def test_get_run_not_found(self, config_path):
        """Test getting non-existent run raises KeyError."""
        loader = BacktestConfigLoader(config_path)
        with pytest.raises(KeyError, match="not found"):
            loader.get_run("nonexistent_run")

    def test_run_references_unknown_instrument(self, tmp_path):
        """Test run referencing unknown instrument raises ValueError."""
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text("""
instruments:
  BTCUSDT:
    venue: BINANCE
    bar_spec: 15-MINUTE-LAST-EXTERNAL
    base_currency: BTC
    quote_currency: USDT

factors:
  test_factor:
    name: Test
    expression: "Clip(ZScore($close, 100), -2, 2)"
    description: Test

runs:
  bad_run:
    instrument: UNKNOWN  # Unknown instrument
    factor: test_factor
    enabled: true
""")

        with pytest.raises(ValueError, match="unknown instrument"):
            BacktestConfigLoader(config_file)

    def test_run_references_unknown_factor(self, tmp_path):
        """Test run referencing unknown factor raises ValueError."""
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text("""
instruments:
  BTCUSDT:
    venue: BINANCE
    bar_spec: 15-MINUTE-LAST-EXTERNAL
    base_currency: BTC
    quote_currency: USDT

factors:
  test_factor:
    name: Test
    expression: "Clip(ZScore($close, 100), -2, 2)"
    description: Test

runs:
  bad_run:
    instrument: BTCUSDT
    factor: UNKNOWN  # Unknown factor
    enabled: true
""")

        with pytest.raises(ValueError, match="unknown factor"):
            BacktestConfigLoader(config_file)


class TestBackwardCompatibility:
    """Tests for backward compatibility with FactorConfigLoader."""

    def test_factorconfigloader_alias(self, config_path):
        """Test FactorConfigLoader is an alias for BacktestConfigLoader."""
        loader = FactorConfigLoader(config_path)
        assert isinstance(loader, BacktestConfigLoader)

    def test_old_api_still_works(self, config_path):
        """Test old API methods still work."""
        loader = FactorConfigLoader(config_path)

        # Old methods
        factors = loader.list_factors()
        assert len(factors) > 0

        factor = loader.get_factor("amt_momentum")
        assert factor.name == "AMT Momentum"

        defaults = loader.get_defaults()
        assert "zscore_period" in defaults

    def test_new_api_available(self, config_path):
        """Test new API is available even when using old alias."""
        loader = FactorConfigLoader(config_path)

        # New methods
        assert len(loader.instruments) > 0
        assert len(loader.runs) > 0

        run_ids = loader.list_runs()
        assert len(run_ids) > 0

        run = loader.get_run(run_ids[0])
        assert run.run_id == run_ids[0]


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_empty_config(self, tmp_path):
        """Test loading empty config file."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        # Should not raise, but have empty collections
        loader = BacktestConfigLoader(config_file)
        assert len(loader.instruments) == 0
        assert len(loader.factors) == 0
        assert len(loader.runs) == 0

    def test_missing_file(self, tmp_path):
        """Test loading non-existent file raises error."""
        nonexistent = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            BacktestConfigLoader(nonexistent)

    def test_defaults_optional(self, tmp_path):
        """Test defaults section is optional."""
        config_file = tmp_path / "no_defaults.yaml"
        config_file.write_text("""
instruments: {}
factors: {}
runs: {}
""")

        loader = BacktestConfigLoader(config_file)
        defaults = loader.get_defaults()
        assert defaults == {}

    def test_risk_config_optional(self, tmp_path):
        """Test risk_management section is optional."""
        config_file = tmp_path / "no_risk.yaml"
        config_file.write_text("""
instruments: {}
factors: {}
runs: {}
""")

        loader = BacktestConfigLoader(config_file)
        assert loader.risk_config is None

    def test_execution_config_optional(self, tmp_path):
        """Test execution section is optional."""
        config_file = tmp_path / "no_execution.yaml"
        config_file.write_text("""
instruments: {}
factors: {}
runs: {}
""")

        loader = BacktestConfigLoader(config_file)
        assert loader.execution_config is None
