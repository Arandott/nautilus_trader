"""Online alpha models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(slots=True)
class RLSParams:
    forgetting: float = 0.995
    ridge: float = 1.0
    a_max_bps: float = 3.0


class RecursiveLeastSquaresAlpha:
    """Simple RLS with forgetting factor."""

    def __init__(self, dimension: int, params: RLSParams) -> None:
        self._w = np.zeros(dimension, dtype=float)
        self._P = np.eye(dimension, dtype=float) * params.ridge
        self._forget = params.forgetting
        self._max = params.a_max_bps

    def update(self, x: Iterable[float], target_bps: float) -> None:
        vec = np.asarray(list(x), dtype=float)
        y = float(target_bps)
        P = self._P
        w = self._w

        denominator = self._forget + vec @ P @ vec
        if denominator <= 0:
            return

        k = (P @ vec) / denominator
        error = y - vec @ w
        self._w = w + k * error
        self._P = (P - np.outer(k, vec) @ P) / self._forget

    def predict(self, x: Iterable[float]) -> float:
        vec = np.asarray(list(x), dtype=float)
        return float(np.clip(vec @ self._w, -self._max, self._max))

    @property
    def weights(self):
        return self._w.copy()
