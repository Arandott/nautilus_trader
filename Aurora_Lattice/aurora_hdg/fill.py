"""Fill probability models."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nautilus_trader.model.enums import OrderSide


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _clamp_decay(decay: float) -> float:
    return max(0.0, min(0.999999, decay))


@dataclass(slots=True)
class QueueStats:
    lambda_mo: float = 0.0
    lambda_cancel: float = 0.0
    mean_mo: float = 0.0
    var_mo: float = 0.0
    touch_rate: float = 0.0

    def update(self, mo_rate: float, cxl_rate: float, mean_mo: float, var_mo: float, decay: float):
        decay = _clamp_decay(decay)
        self.lambda_mo = decay * self.lambda_mo + (1 - decay) * mo_rate
        self.lambda_cancel = decay * self.lambda_cancel + (1 - decay) * cxl_rate
        self.mean_mo = decay * self.mean_mo + (1 - decay) * mean_mo
        self.var_mo = decay * self.var_mo + (1 - decay) * var_mo

    def update_touch(self, hit: bool, dt_s: float, decay: float) -> None:
        decay = _clamp_decay(decay)
        rate_sample = (1.0 / max(dt_s, 1e-6)) if hit else 0.0
        self.touch_rate = decay * self.touch_rate + (1 - decay) * rate_sample


class FillModel:
    """Interface."""

    def p_fill(
        self,
        side: OrderSide,
        distance: float,
        mu: float,
        sigma_px: float,
        horizon_s: float,
        queue_ahead: float,
        stats: QueueStats,
    ) -> float:
        raise NotImplementedError


class HittingQueueFillModel(FillModel):
    """Two stage fill probability approximation."""

    def __init__(self, min_p: float = 0.05, tick_size: float = 0.01, use_empirical_touch: bool = False) -> None:
        self._min = min_p
        self._use_empirical_touch = use_empirical_touch
        self._empirical_threshold = 1.5 * max(tick_size, 1e-9)

    def p_touch(
        self,
        side: OrderSide,
        distance: float,
        mu: float,
        sigma_px: float,
        horizon_s: float,
        stats: QueueStats | None,
    ) -> float:
        if horizon_s <= 0:
            return 0.0

        if (
            self._use_empirical_touch
            and stats is not None
            and distance <= self._empirical_threshold
            and stats.touch_rate > 0.0
        ):
            prob = 1.0 - math.exp(-stats.touch_rate * horizon_s)
            return max(0.0, min(1.0, prob))

        if sigma_px <= 0:
            return 0.0

        signed = -distance if side == OrderSide.BUY else distance
        drift = mu * horizon_s
        denom = sigma_px * math.sqrt(horizon_s)
        z = (signed - drift) / denom
        return max(0.0, min(1.0, _norm_cdf(z)))

    def p_queue(self, queue_ahead: float, stats: QueueStats, horizon_s: float) -> float:
        lam = stats.lambda_mo + stats.lambda_cancel
        if lam <= 0 or horizon_s <= 0:
            return 0.0

        mean = lam * horizon_s * max(stats.mean_mo, 1e-6)
        var = lam * horizon_s * max(stats.var_mo, 1e-6)
        std = math.sqrt(var)
        if std <= 0:
            return 0.0

        z = (mean - queue_ahead) / std
        return max(0.0, min(1.0, _norm_cdf(z)))

    def p_fill(
        self,
        side: OrderSide,
        distance: float,
        mu: float,
        sigma_px: float,
        horizon_s: float,
        queue_ahead: float,
        stats: QueueStats,
    ) -> float:
        p_touch = self.p_touch(side, distance, mu, sigma_px, horizon_s, stats)
        p_queue = self.p_queue(queue_ahead, stats, horizon_s)
        p = p_touch * p_queue
        return max(self._min if p_touch > 0 else 0.0, min(1.0, p))
