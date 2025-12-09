"""Validate RLS PyO3 binding learns from delayed labels in a streaming simulation."""

from __future__ import annotations

import math
import os
from collections import deque

from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings


EXTRA_PREDICTS = max(0, int(os.getenv("RLS_EXTRA_PREDICTS", "20000")))


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Simple Pearson correlation without external deps."""
    n = min(len(xs), len(ys))
    if n == 0:
        return 0.0
    xs = xs[-n:]
    ys = ys[-n:]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def test_rls_alpha_tracks_streaming_returns() -> None:
    """Simulate predict-then-delayed-update loop and ensure correlation with ground truth."""
    params = aurora_bindings.RlsParams(forgetting=0.985, ridge=1.0, a_max_bps=250.0)
    model = aurora_bindings.RlsAlpha(dimension=3, params=params)

    true_w = (35.0, -18.0, 1200.0)
    lag = 5
    mid = 100.0
    pending: deque[tuple[tuple[float, ...], float, float]] = deque()
    preds: list[float] = []
    realized: list[float] = []

    for t in range(180):
        imbalance = math.tanh((t - 60) / 25.0)
        micro_skew = 0.5 * math.sin(0.05 * t)
        sigma_rel = 0.001 + 0.0004 * (1.0 + math.sin(0.03 * t))
        features = (imbalance, micro_skew, sigma_rel)
        for _ in range(EXTRA_PREDICTS):
            model.predict(list(features))
        pred = model.predict(list(features))
        pending.append((features, mid, pred))

        signal_bps = sum(w * f for w, f in zip(true_w, features))
        noise_bps = 0.3 * math.sin(0.11 * t)
        ret_bps = signal_bps + noise_bps
        mid *= 1.0 + ret_bps / 1e4

        if len(pending) > lag:
            feat, prev_mid, prev_pred = pending.popleft()
            realized_bps = ((mid - prev_mid) / prev_mid) * 1e4
            realized.append(realized_bps)
            preds.append(prev_pred)
            model.update(list(feat), realized_bps)

    assert len(preds) > 50
    corr = _pearson(preds[-60:], realized[-60:])
    assert corr > 0.6

    learned_w = model.weights()
    assert len(learned_w) == 3
    alignment = sum(w * gt for w, gt in zip(learned_w, true_w))
    assert alignment > 0

if __name__ == "__main__":
    test_rls_alpha_tracks_streaming_returns()