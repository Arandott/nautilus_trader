"""Smoke tests covering Aurora HDG strategy wiring."""

from __future__ import annotations

from pathlib import Path

from Aurora_Lattice.aurora_hdg import AuroraHdgStrategy, load_config


def test_strategy_instantiation_from_default_config() -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
    cfg = load_config(cfg_path)
    strategy = AuroraHdgStrategy(cfg)
    assert strategy.config.instrument_id == cfg.instrument_id
    assert strategy.config.grid.levels > 0
