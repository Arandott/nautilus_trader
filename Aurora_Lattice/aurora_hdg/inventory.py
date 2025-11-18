"""Inventory and grid sizing utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from nautilus_trader.model.enums import OrderSide

from .config import GridParams, InventoryParams


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_target_inventory(
    alpha_bps: float,
    sigma_px: float,
    tau_s: float,
    params: InventoryParams,
) -> float:
    if sigma_px <= 0 or tau_s <= 0:
        return 0.0
    target = (params.kappa_alpha * alpha_bps) / (params.gamma * (sigma_px**2 * tau_s))
    return clip(target, -params.i_max, params.i_max)


def compute_center(
    microprice: float,
    current_inventory: float,
    target_inventory: float,
    delta: float,
    alpha_bps: float,
    params: InventoryParams,
) -> float:
    skew_term = params.beta_i * (current_inventory - target_inventory) * delta
    alpha_term = params.theta_i * alpha_bps * delta * 0.01
    return microprice + skew_term - alpha_term


def base_delta(
    sigma_px: float,
    tick_size: float,
    params: GridParams,
    fee_buffer_price: float,
) -> float:
    raw = params.k_sigma * sigma_px + params.k_s * tick_size + params.k_f * fee_buffer_price
    return max(tick_size, raw)


def level_distances(levels: int, delta: float) -> List[float]:
    return [(i + 0.5) * delta for i in range(levels)]


def level_quantity(
    level_index: int,
    params: InventoryParams,
    current_inventory: float,
    target_inventory: float,
    side: OrderSide,
) -> float:
    q = params.base_qty * (params.eta ** level_index)
    inv_skew = params.theta_i * (current_inventory - target_inventory) / params.i_max
    adjust = 1.0 - inv_skew if side == OrderSide.BUY else 1.0 + inv_skew
    qty = q * clip(adjust, params.q_min / params.base_qty, params.q_max / params.base_qty)
    return max(params.q_min, min(params.q_max, qty))
