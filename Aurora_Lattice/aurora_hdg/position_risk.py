"""Position TTL monitor and taker safety valve."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .config import PositionRiskParams, TakerParams


@dataclass(slots=True)
class PositionRiskDecision:
    trigger: bool
    target_qty: float  # signed target inventory to move toward


class PositionRiskMonitor:
    def __init__(self, params: PositionRiskParams, taker: TakerParams, i_max: float) -> None:
        self.params = params
        self.taker = taker
        self.i_max = max(i_max, 1e-9)
        self._t_since_flat_ns: int = 0
        self._last_update_ns: int = 0
        self._last_taker_ns: int = 0

    def reset(self) -> None:
        self._t_since_flat_ns = 0
        self._last_update_ns = 0

    def _threshold(self) -> float:
        return self.params.t_since_flat_threshold_I_ratio * self.i_max

    def update_clock(self, ts_ns: int) -> None:
        if self._last_update_ns == 0:
            self._last_update_ns = ts_ns
            return
        dt = ts_ns - self._last_update_ns
        self._last_update_ns = ts_ns
        self._t_since_flat_ns += max(dt, 0)

    def on_inventory(
        self, inventory_qty: float, target_inventory: float, regime: str, ts_ns: int
    ) -> PositionRiskDecision:
        self.update_clock(ts_ns)
        if abs(inventory_qty - target_inventory) < self._threshold():
            self._t_since_flat_ns = 0
            return PositionRiskDecision(trigger=False, target_qty=target_inventory)

        # Pick regime-specific H_max.
        if regime == "CHAOS":
            h_max_ms = self.params.H_max_chaos_ms
        elif regime.startswith("TREND"):
            h_max_ms = self.params.H_max_trend_ms
        else:
            h_max_ms = self.params.H_max_normal_ms

        if self._t_since_flat_ns / 1e6 < h_max_ms:
            return PositionRiskDecision(trigger=False, target_qty=target_inventory)

        # TTL exceeded -> suggest taker toward I*.
        return PositionRiskDecision(trigger=True, target_qty=target_inventory)

    def allow_taker(self, ts_ns: int) -> bool:
        if ts_ns - self._last_taker_ns < self.taker.cooldown_ms * 1_000_000:
            return False
        self._last_taker_ns = ts_ns
        return True


def calc_mo_slippage_price(mid: float, side: str, max_slippage_bps: float) -> float:
    """Simple protective limit price for IOC (bps from mid)."""
    s = side.upper()
    delta = mid * max_slippage_bps / 10_000.0
    return mid + delta if s == "BUY" else mid - delta
