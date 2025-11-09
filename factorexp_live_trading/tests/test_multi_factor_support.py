from __future__ import annotations

from pathlib import Path

import pytest

from factorexp_live_trading.config.security import SecureConfigManager
from factorexp_live_trading.config.strategy_config import FactorExpLiveStrategyConfig
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


def _make_config(**overrides) -> FactorExpLiveStrategyConfig:
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
    bar_type = BarType.from_str("BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL")
    return FactorExpLiveStrategyConfig(instrument_id=instrument_id, bar_type=bar_type, **overrides)


def test_strategy_config_defaults_to_single_factor_tuple():
    config = _make_config()

    assert config.factor_id == "vwap_return_std"
    assert config.factor_ids == ("vwap_return_std",)


def test_strategy_config_normalizes_factor_ids_sequence():
    config = _make_config(factor_ids=("alpha", "beta", "gamma"))

    assert config.factor_id == "alpha"
    assert config.factor_ids == ("alpha", "beta", "gamma")


def test_strategy_config_parses_comma_separated_factor_ids():
    config = _make_config(factor_ids="alpha, beta ,gamma,,")

    assert config.factor_id == "alpha"
    assert config.factor_ids == ("alpha", "beta", "gamma")


def test_strategy_config_rejects_empty_factor_ids():
    with pytest.raises(ValueError):
        _make_config(factor_ids=[])


def test_strategy_config_allows_disabling_segment_stop_loss():
    config = _make_config(segment_stop_loss_pct=0.0)

    assert config.segment_stop_loss_pct == 0.0


def test_secure_config_manager_parses_factor_ids(tmp_path, monkeypatch):
    manager = SecureConfigManager(project_root=Path(tmp_path))

    monkeypatch.setenv("FACTOREXP_FACTOR_IDS", "foo, bar ,baz")
    params = manager.get_factorexp_parameters()

    assert params["factor_ids"] == ("foo", "bar", "baz")
    assert params["factor_id"] == "vwap_return_std"

    monkeypatch.delenv("FACTOREXP_FACTOR_IDS")


def test_secure_config_manager_parses_segment_risk_overrides(tmp_path, monkeypatch):
    manager = SecureConfigManager(project_root=Path(tmp_path))

    monkeypatch.setenv("FACTOREXP_SEGMENT_STOP_LOSS_PCT", "0.025")
    monkeypatch.setenv("FACTOREXP_SEGMENT_FREEZE_BARS", "144")
    params = manager.get_factorexp_parameters()

    assert params["segment_stop_loss_pct"] == 0.025
    assert params["segment_freeze_bars"] == 144

    monkeypatch.delenv("FACTOREXP_SEGMENT_STOP_LOSS_PCT")
    monkeypatch.delenv("FACTOREXP_SEGMENT_FREEZE_BARS")
