"""Risk controls and hedging helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

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
    def __init__(self, params: RiskParams, inventory: InventoryParams) -> None:
        self.params = params
        self.inventory = inventory
        self.state = RiskState.NORMAL
        self._last_sigma = 0.0
        self._last_hedge_ns = 0

    def on_metrics(
        self,
        sigma_rel: float,
        base_sigma: float,
        inventory_qty: float,
        now_ns: int,
    ) -> RiskDecision:
        sigma_ratio = sigma_rel / max(base_sigma, 1e-9)
        state = self.state
        reason = None
        widen_factor = 1.0
        reduce_levels = 0

        if sigma_ratio >= self.params.shock_mode_sigma_mult:
            state = RiskState.PAUSE
            reason = "vol_shock"
        elif sigma_ratio >= (self.params.shock_mode_sigma_mult * 0.7):
            state = RiskState.WIDEN
            widen_factor = 1.5
            reduce_levels = 1
            reason = "vol_spike"
        else:
            state = RiskState.NORMAL

        self.state = state
        hedge_qty = self._maybe_hedge(inventory_qty, now_ns)

        return RiskDecision(
            state=state,
            widen_factor=widen_factor,
            reduce_levels=reduce_levels,
            hedge_qty=hedge_qty,
            reason=reason,
        )

    def _maybe_hedge(self, qty: float, now_ns: int) -> float:
        if abs(qty) < self.inventory.i_soft:
            return 0.0
        elapsed = (now_ns - self._last_hedge_ns) / 1e6  # ms
        if elapsed < self.params.hedge_cooldown_ms:
            return 0.0

        hedge_qty = self.params.hedge_min_qty if qty > 0 else -self.params.hedge_min_qty
        self._last_hedge_ns = now_ns
        return hedge_qty
