"""Unit tests for inventory/grid helpers."""

from __future__ import annotations

from Aurora_Lattice.aurora_hdg.config import InventoryParams
from Aurora_Lattice.tests.inventory_helpers import compute_center, compute_target_inventory


def _inventory_params() -> InventoryParams:
    return InventoryParams(
        i_max=10.0,
        i_soft=6.0,
        gamma=2.0e-6,
        kappa_alpha=0.8,
        beta_i=0.6,
        theta_i=0.8,
        base_qty=1.0,
        eta=0.8,
        q_min=0.2,
        q_max=2.0,
    )


def test_compute_target_inventory_is_clipped() -> None:
    params = _inventory_params()
    target = compute_target_inventory(alpha_bps=50.0, sigma_px=100.0, tau_s=0.3, params=params)
    assert -params.i_max <= target <= params.i_max


def test_compute_center_moves_against_inventory_skew() -> None:
    params = _inventory_params()
    center_long = compute_center(
        microprice=100.0,
        current_inventory=5.0,
        target_inventory=0.0,
        delta=0.5,
        alpha_bps=0.0,
        params=params,
    )
    center_short = compute_center(
        microprice=100.0,
        current_inventory=-5.0,
        target_inventory=0.0,
        delta=0.5,
        alpha_bps=0.0,
        params=params,
    )
    # Long inventory should skew center lower to entice sells; short does the opposite.
    assert center_long < 100.0
    assert center_short > 100.0
