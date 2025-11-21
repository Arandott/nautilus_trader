"""Inventory and grid sizing utilities."""

from __future__ import annotations

from typing import List

from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings
from nautilus_trader.model.enums import OrderSide

from .config import AuroraHDGConfig, GridParams, InventoryParams


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_target_inventory(
    alpha_bps: float,
    sigma_px: float,
    tau_s: float,
    params: InventoryParams,
) -> float:
    # target = clip( (κ_alpha * α) / (γ * σ_px^2 * τ), [-i_max, i_max] )
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
    # center = microprice + ( -κ_I (I - I*)/I_max + κ_alpha * α ) * Δ
    inv_term = params.beta_i * (current_inventory - target_inventory) / max(params.i_max, 1e-9)
    alpha_term = params.theta_i * alpha_bps / 10_000.0
    skew = -inv_term + alpha_term
    return microprice + skew * delta


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


def level_distances(levels: int, delta: float) -> List[float]:
    return [(i + 0.5) * delta for i in range(levels)]


def level_quantity(
    level_index: int,
    params: InventoryParams,
    current_inventory: float,
    target_inventory: float,
    side: OrderSide,
) -> float:
    # q_level = base_qty * η^level * clamp(1 ± θ_i (I - I*) / i_max, q_min/base, q_max/base)
    q = params.base_qty * (params.eta ** level_index)
    inv_skew = params.theta_i * (current_inventory - target_inventory) / params.i_max
    adjust = 1.0 - inv_skew if side == OrderSide.BUY else 1.0 + inv_skew
    qty = q * clip(adjust, params.q_min / params.base_qty, params.q_max / params.base_qty)
    return max(params.q_min, min(params.q_max, qty))


def build_grid_planner(config: AuroraHDGConfig):
    """Construct the PyO3 Aurora grid planner with settings from strategy config."""
    return aurora_bindings.AuroraGridPlanner(
        grid_levels=config.grid.levels,
        k_sigma=config.grid.k_sigma,
        k_s=config.grid.k_s,
        k_f=config.grid.k_f,
        fee_buffer_bps=config.grid.fee_buffer_bps,
        delta_entry_ticks=config.grid.delta_entry_ticks,
        exit_cost_bps=config.grid.exit_cost_bps,
        q_mm=config.grid.q_mm,
        unfilled_penalty_ticks=config.grid.unfilled_penalty_ticks,
        i_max=config.inventory.i_max,
        i_soft=config.inventory.i_soft,
        gamma=config.inventory.gamma,
        kappa_alpha=config.inventory.kappa_alpha,
        beta_i=config.inventory.beta_i,
        theta_i=config.inventory.theta_i,
        base_qty=config.inventory.base_qty,
        eta=config.inventory.eta,
        q_min=config.inventory.q_min,
        q_max=config.inventory.q_max,
        msg_rate_budget=config.exec.msg_rate_budget,
        tick_size=config.tick_size,
        min_p_fill=config.fill_model.min_p_fill,
        use_empirical_touch=config.fill_model.use_empirical_touch,
    )
