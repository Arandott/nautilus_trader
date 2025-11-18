"""Unit tests for Aurora HDG fill model helpers."""

from __future__ import annotations

import math

from aurora_hdg.fill import HittingQueueFillModel, QueueStats
from nautilus_trader.model.enums import OrderSide


def _base_stats() -> QueueStats:
    return QueueStats(lambda_mo=5.0, lambda_cancel=1.0, mean_mo=1.0, var_mo=1.0)


def test_empirical_touch_overrides_analytic() -> None:
    stats = _base_stats()
    stats.touch_rate = 20.0  # hits per second at best level
    model = HittingQueueFillModel(min_p=0.01, tick_size=0.1, use_empirical_touch=True)

    horizon = 0.1
    distance = 0.05  # within empirical threshold (1.5 * tick)

    p_fill = model.p_fill(
        side=OrderSide.BUY,
        distance=distance,
        mu=0.0,
        sigma_px=1.0,
        horizon_s=horizon,
        queue_ahead=0.5,
        stats=stats,
    )
    p_queue = model.p_queue(queue_ahead=0.5, stats=stats, horizon_s=horizon)
    expected_touch = 1.0 - math.exp(-stats.touch_rate * horizon)

    assert p_queue > 0
    assert math.isclose(p_fill / p_queue, expected_touch, rel_tol=1e-6)


def test_analytic_touch_used_when_empirical_disabled() -> None:
    stats = _base_stats()
    stats.touch_rate = 20.0
    analytic_model = HittingQueueFillModel(min_p=0.01, tick_size=0.1, use_empirical_touch=False)

    empirical_model = HittingQueueFillModel(min_p=0.01, tick_size=0.1, use_empirical_touch=True)
    stats_empirical = _base_stats()
    stats_empirical.touch_rate = 20.0

    horizon = 0.1
    kwargs = dict(
        side=OrderSide.BUY,
        distance=0.05,
        mu=0.0,
        sigma_px=1.0,
        horizon_s=horizon,
        queue_ahead=0.5,
    )
    analytic = analytic_model.p_fill(stats=stats, **kwargs)
    empirical = empirical_model.p_fill(stats=stats_empirical, **kwargs)

    assert not math.isclose(analytic, empirical)
