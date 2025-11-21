"""Risk controls backed by PyO3 advisors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings

from .config import InventoryParams, RiskParams


class RiskState(Enum):
    NORMAL = auto()
    WIDEN = auto()
    PAUSE = auto()


@dataclass(slots=True)
class RiskDecision:
    state: RiskState
    widen_factor: float = 1.0
    reduce_levels: int = 0
    hedge_qty: float = 0.0
    reason: str | None = None


class RiskStateMachine:
    """Thin wrapper around the Rust/PyO3 risk advisor."""

    def __init__(self, params: RiskParams, inventory: InventoryParams) -> None:
        self.params = params
        self.inventory = inventory
        self._advisor = aurora_bindings.AuroraRiskAdvisor(
            vol_shock_sigma_mult=params.shock_mode_sigma_mult,
            inventory_soft_limit=inventory.i_soft,
            hedge_cooldown_ms=params.hedge_cooldown_ms,
            hedge_min_qty=params.hedge_min_qty,
        )
        self._state_map = {
            aurora_bindings.AuroraRiskState.NORMAL: RiskState.NORMAL,
            aurora_bindings.AuroraRiskState.WIDEN: RiskState.WIDEN,
            aurora_bindings.AuroraRiskState.PAUSE: RiskState.PAUSE,
        }

    def on_metrics(
        self,
        sigma_rel: float,
        base_sigma: float,
        inventory_qty: float,
        now_ns: int,
    ) -> RiskDecision:
        decision = self._advisor.advise(
            sigma_rel=sigma_rel,
            base_sigma=base_sigma,
            inventory_qty=inventory_qty,
            now_ns=now_ns,
        )
        state = self._state_map.get(decision.state, RiskState.NORMAL)
        return RiskDecision(
            state=state,
            widen_factor=decision.widen_factor,
            reduce_levels=int(decision.reduce_levels),
            hedge_qty=decision.hedge_qty,
            reason=decision.reason,
        )
