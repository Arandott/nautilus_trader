"""Regime detection for Aurora Lattice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .config import RegimeParams


class Regime(Enum):
    NORMAL = auto()
    TREND_UP = auto()
    TREND_DOWN = auto()
    CHAOS = auto()


@dataclass(slots=True)
class RegimeDecision:
    regime: Regime
    delta_multiplier: float = 1.0
    level_reduction: int = 0


class RegimeMachine:
    """State machine with hysteresis for NORMAL/TREND/CHAOS."""

    def __init__(self, params: RegimeParams) -> None:
        self.params = params
        self._regime = Regime.NORMAL
        self._last_switch_ns: int = 0

    @property
    def regime(self) -> Regime:
        return self._regime

    def _hysteresis_ok(self, ts_ns: int) -> bool:
        elapsed_ms = (ts_ns - self._last_switch_ns) / 1e6
        return elapsed_ms >= self.params.hysteresis_ms

    def update(
        self,
        alpha_bps: float,
        delta_ratio: float,
        mo_imbalance: float,
        sigma_rel: float,
        base_sigma: float,
        ts_ns: int,
    ) -> RegimeDecision:
        if self.params.mode == "normal_only":
            self._regime = Regime.NORMAL
            return RegimeDecision(regime=self._regime)

        # CHAOS: volatility blow-up or NaN feeds.
        if base_sigma > 0 and sigma_rel / base_sigma >= self.params.chaos_sigma_mult:
            if self._regime != Regime.CHAOS and self._hysteresis_ok(ts_ns):
                self._regime = Regime.CHAOS
                self._last_switch_ns = ts_ns
            return RegimeDecision(regime=self._regime, delta_multiplier=2.0, level_reduction=2)

        trend_candidate = abs(alpha_bps) >= self.params.alpha_gate_bps and (
            delta_ratio >= self.params.trend_delta_ratio_threshold
            or mo_imbalance >= self.params.mo_imbalance_threshold
        )

        if trend_candidate and self._hysteresis_ok(ts_ns):
            self._regime = Regime.TREND_UP if alpha_bps > 0 else Regime.TREND_DOWN
            self._last_switch_ns = ts_ns
        elif not trend_candidate and self._hysteresis_ok(ts_ns):
            self._regime = Regime.NORMAL
            self._last_switch_ns = ts_ns

        if self._regime in (Regime.TREND_UP, Regime.TREND_DOWN):
            return RegimeDecision(regime=self._regime, delta_multiplier=1.2, level_reduction=1)

        return RegimeDecision(regime=self._regime)
