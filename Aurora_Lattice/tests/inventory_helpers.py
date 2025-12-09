"""Test-only helpers mirroring inventory/grid formulas."""

from __future__ import annotations

from Aurora_Lattice.aurora_hdg.config import InventoryParams


def _clip(value: float, lo: float, hi: float) -> float:
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
    return _clip(target, -params.i_max, params.i_max)


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
