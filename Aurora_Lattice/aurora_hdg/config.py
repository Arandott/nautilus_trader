"""Aurora HDG configuration models leveraging Nautilus config infra."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import msgspec
except ImportError:  # pragma: no cover
    msgspec = None
    import json as stdlib_json
else:
    stdlib_json = None

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from nautilus_trader.common.config import NautilusConfig
from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.config import ImportableStrategyConfig, StrategyConfig


def build_strategy_config(data: dict[str, Any]) -> AuroraHDGConfig:
    instrument_id = data.get("instrument_id")
    if not instrument_id:
        raise ValueError("`instrument_id` missing in config file.")

    def build(section: str, cls):
        if section not in data:
            raise ValueError(f"Section `{section}` missing in config file.")
        return cls(**data[section])

    return AuroraHDGConfig(
        instrument_id=InstrumentId.from_str(instrument_id),
        grid=build("grid", GridParams),
        inventory=build("inventory", InventoryParams),
        alpha=build("alpha", AlphaParams),
        fill_model=build("fill_model", FillModelParams),
        exec=build("exec", ExecParams),
        risk=build("risk", RiskParams),
        regime=build("regime", RegimeParams) if "regime" in data else RegimeParams(),
        position_risk=build("position_risk", PositionRiskParams)
        if "position_risk" in data
        else PositionRiskParams(),
        taker=build("taker", TakerParams) if "taker" in data else TakerParams(),
        tick_size=data.get("tick_size", 0.01),
        base_symbol=data.get("base_symbol", "UNKNOWN"),
        strategy_id=data.get("strategy_id"),
        order_id_tag=data.get("order_id_tag"),
    )


class GridParams(NautilusConfig, frozen=True):
    levels: PositiveInt = 6
    k_sigma: PositiveFloat = 0.9
    k_s: float = 0.5
    k_f: float = 0.6
    fee_buffer_bps: float = 3.0
    delta_entry_ticks: float = 1.0
    exit_cost_bps: float = 0.0
    q_mm: float = 0.0
    unfilled_penalty_ticks: float = 0.0
    reanchor_rho: float = 1.2
    reanchor_timeout_ms: PositiveInt = 400


class InventoryParams(NautilusConfig, frozen=True):
    i_max: float
    i_soft: float
    gamma: float
    kappa_alpha: float
    beta_i: float = 0.6
    theta_i: float = 0.8
    base_qty: float = 1.0
    eta: float = 0.35
    q_min: float = 0.2
    q_max: float = 2.0


class AlphaParams(NautilusConfig, frozen=True):
    tau_ms: PositiveInt = 300
    a_max_bps: float = 3.0
    a_gate_bps: float = 1.2
    beta_alpha: float = 0.25
    kappa_delta: float = 0.25
    rls_forgetting: float = 0.995


class FillModelParams(NautilusConfig, frozen=True):
    tau_ms: PositiveInt = 300
    ttl_ratio: float = 0.7
    lambda_window_ms: PositiveInt = 300
    use_empirical_touch: bool = True
    min_p_fill: float = 0.15


class ExecParams(NautilusConfig, frozen=True):
    msg_rate_budget: PositiveInt = 40
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 2.0


class RiskParams(NautilusConfig, frozen=True):
    shock_mode_sigma_mult: float = 2.5
    hedge_cooldown_ms: PositiveInt = 800
    hedge_min_qty: float = 1.0


class RegimeParams(NautilusConfig, frozen=True):
    mode: str = "full"  # full | normal_only
    trend_delta_ratio_threshold: float = 0.6
    mo_imbalance_threshold: float = 2.5
    alpha_gate_bps: float = 1.2
    chaos_sigma_mult: float = 4.0
    hysteresis_ms: PositiveInt = 800


class PositionRiskParams(NautilusConfig, frozen=True):
    H_max_normal_ms: PositiveInt = 2500
    H_max_trend_ms: PositiveInt = 1500
    H_max_chaos_ms: PositiveInt = 800
    t_since_flat_threshold_I_ratio: float = 0.1


class TakerParams(NautilusConfig, frozen=True):
    taker_budget_bps_per_hour: float = 8.0
    taker_clip_qty: float = 2.0
    taker_max_slippage_bps: float = 3.0
    cooldown_ms: PositiveInt = 500


class AuroraHDGConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    grid: GridParams
    inventory: InventoryParams
    alpha: AlphaParams
    fill_model: FillModelParams
    exec: ExecParams
    risk: RiskParams
    regime: RegimeParams = RegimeParams()
    position_risk: PositionRiskParams = PositionRiskParams()
    taker: TakerParams = TakerParams()
    tick_size: PositiveFloat = 0.01
    base_symbol: str = "UNKNOWN"


def read_config_data(path: Path) -> dict[str, Any]:
    raw = path.read_text()
    if yaml is not None and path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(raw)
    if msgspec is not None:
        return msgspec.json.decode(raw.encode())
    return stdlib_json.loads(raw)


def load_config(path: str | Path) -> AuroraHDGConfig:
    """Load config data from YAML/JSON into structured config."""
    p = Path(path)
    data = read_config_data(p)
    strategy_data = data.get("strategy", data)
    return build_strategy_config(strategy_data)


def to_importable_config(config: AuroraHDGConfig) -> ImportableStrategyConfig:
    """
    Build an :class:`ImportableStrategyConfig` for use with StrategyFactory.
    """

    return ImportableStrategyConfig(
        strategy_path="Aurora_Lattice.aurora_hdg.strategy:AuroraHdgStrategy",
        config_path="Aurora_Lattice.aurora_hdg.config:AuroraHDGConfig",
        config=config.json_primitives(),
    )
