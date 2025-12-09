"""Inventory and grid sizing utilities."""

from __future__ import annotations

from .config import GridParams


def base_delta(
    sigma_px: float,
    tick_size: float,
    params: GridParams,
    fee_buffer_price: float,
    tau_fill_s: float,
) -> float:
    # Δ = round_to_tick(k_sigma * σ_px * sqrt(τ_fill) + k_s * tick + k_f * fee_buffer)
    sigma_term = params.k_sigma * sigma_px * (tau_fill_s**0.5)
    raw = sigma_term + params.k_s * tick_size + params.k_f * fee_buffer_price
    if tick_size <= 0:
        return max(tick_size, raw)
    return max(tick_size, round(raw / tick_size) * tick_size)
