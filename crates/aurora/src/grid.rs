// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing.permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! Grid planning and level sizing logic.

use crate::fill::{FillModel, QueueStats};
use log::info;
use nautilus_model::{enums::OrderSide, orderbook::OrderBook};

/// Static grid sizing parameters.
#[derive(Debug, Clone)]
pub struct GridParams {
    pub levels: usize,
    pub k_sigma: f64,
    pub k_s: f64,
    pub k_f: f64,
    pub fee_buffer_bps: f64,
    pub delta_entry_ticks: f64,
    pub exit_cost_bps: f64,
    pub q_mm: f64,
    pub unfilled_penalty_ticks: f64,
}

/// Inventory skew parameters.
#[derive(Debug, Clone)]
pub struct InventoryParams {
    pub i_max: f64,
    pub i_soft: f64,
    pub gamma: f64,
    pub kappa_alpha: f64,
    pub beta_i: f64,
    pub theta_i: f64,
    pub base_qty: f64,
    pub eta: f64,
    pub q_min: f64,
    pub q_max: f64,
}

/// Planner level configuration.
#[derive(Debug, Clone)]
pub struct GridPlannerConfig {
    pub grid: GridParams,
    pub inventory: InventoryParams,
    pub msg_rate_budget: usize,
    pub tick_size: f64,
}

/// Finalized level description returned to Python bindings.
#[derive(Debug, Clone)]
pub struct GridLevel {
    pub side: OrderSide,
    pub price: f64,
    pub quantity: f64,
    pub distance: f64,
    pub edge: f64,
    pub p_fill: f64,
}

/// Aggregated plan metadata.
#[derive(Debug, Clone)]
pub struct GridPlan {
    center: f64,
    delta: f64,
    delta_eff: f64,
    target_inventory: f64,
    orders: Vec<GridLevel>,
}

impl GridPlan {
    #[must_use]
    pub fn center(&self) -> f64 {
        self.center
    }

    #[must_use]
    pub fn delta(&self) -> f64 {
        self.delta
    }

    #[must_use]
    pub fn delta_eff(&self) -> f64 {
        self.delta_eff
    }

    #[must_use]
    pub fn target_inventory(&self) -> f64 {
        self.target_inventory
    }

    #[must_use]
    pub fn orders(&self) -> &[GridLevel] {
        &self.orders
    }
}

impl GridPlan {
    fn empty(center: f64, delta: f64, target_inventory: f64) -> Self {
        Self {
            center,
            delta,
            delta_eff: delta,
            target_inventory,
            orders: Vec::new(),
        }
    }

    fn new(
        center: f64,
        delta: f64,
        delta_eff: f64,
        target_inventory: f64,
        orders: Vec<GridLevel>,
    ) -> Self {
        Self {
            center,
            delta,
            delta_eff,
            target_inventory,
            orders,
        }
    }
}

/// Grid construction engine.
#[derive(Debug, Clone)]
pub struct GridPlanner {
    config: GridPlannerConfig,
    fill_model: FillModel,
    use_fill_model: bool,
}

impl GridPlanner {
    #[must_use]
    pub fn new(config: GridPlannerConfig, fill_model: FillModel, use_fill_model: bool) -> Self {
        Self {
            config,
            fill_model,
            use_fill_model,
        }
    }

    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn plan(
        &self,
        book: &OrderBook,
        mid: f64,
        microprice: f64,
        sigma_px: f64,
        alpha_bps: f64,
        tau_alpha_s: f64,
        tau_fill_s: f64,
        inventory_qty: f64,
        widen_factor: f64,
        reduce_levels: usize,
        bid_stats: &QueueStats,
        ask_stats: &QueueStats,
    ) -> GridPlan {
        let fee_buffer_px = mid * self.config.grid.fee_buffer_bps / 10_000.0;
        let delta = base_delta(
            &self.config.grid,
            sigma_px,
            self.config.tick_size,
            fee_buffer_px,
            tau_fill_s,
        );
        if delta <= 0.0 {
            return GridPlan::empty(microprice, delta, 0.0);
        }
        let exit_cost_px = mid * self.config.grid.exit_cost_bps / 10_000.0;
        let q_mm = self.config.grid.q_mm.clamp(0.0, 1.0);

        let target_inventory =
            target_inventory(alpha_bps, sigma_px, tau_alpha_s, &self.config.inventory);
        let center = compute_center(
            microprice,
            inventory_qty,
            target_inventory,
            delta,
            alpha_bps,
            &self.config.inventory,
        );

        let delta_eff = delta * widen_factor.max(1.0);
        let available_levels = self.config.grid.levels.saturating_sub(reduce_levels);
        if available_levels == 0 {
            return GridPlan::new(center, delta, delta_eff, target_inventory, Vec::new());
        }
        let fee_limit = (self.config.msg_rate_budget / 2).max(1);
        let capped_levels = available_levels.min(fee_limit);

        let mut orders = Vec::with_capacity(self.config.msg_rate_budget);
        for idx in 0..capped_levels {
            let distance = (idx as f64 + 0.5) * delta_eff;
            for side in [OrderSide::Buy, OrderSide::Sell] {
                let price = match side {
                    OrderSide::Buy => center - distance,
                    OrderSide::Sell => center + distance,
                    OrderSide::NoOrderSide => continue,
                };
                if price <= 0.0 {
                    continue;
                }

                let qty = level_quantity(
                    idx,
                    &self.config.inventory,
                    inventory_qty,
                    target_inventory,
                    side,
                );
                if qty <= 0.0 {
                    continue;
                }

                let queue_ahead = queue_ahead(book, side, price);
                let stats = if matches!(side, OrderSide::Buy) {
                    bid_stats
                } else {
                    ask_stats
                };
                let p_fill = if self.use_fill_model {
                    self.fill_model.p_fill(
                        side,
                        distance,
                        0.0,
                        sigma_px,
                        tau_fill_s,
                        queue_ahead,
                        stats,
                    )
                } else {
                    1.0
                };

                let pickoff = 0.5 * sigma_px;
                let entry_penalty = self.config.grid.delta_entry_ticks * self.config.tick_size;
                let edge = distance - fee_buffer_px - pickoff - entry_penalty;
                let exit_penalty = (1.0 - q_mm) * exit_cost_px;
                let unfilled_penalty = (1.0 - p_fill)
                    * self.config.grid.unfilled_penalty_ticks
                    * self.config.tick_size;
                let variance_penalty = (1.0 - p_fill)
                    * self.config.inventory.gamma
                    * inventory_qty.abs()
                    * sigma_px
                    * tau_fill_s.sqrt();
                let expected_value =
                    qty * (p_fill * (edge - exit_penalty) - variance_penalty - unfilled_penalty);
                let side_str = match side {
                    OrderSide::Buy => "BUY",
                    OrderSide::Sell => "SELL",
                    OrderSide::NoOrderSide => "NA",
                };
                info!(
                    target: "aurora::grid_ev",
                    "EV_DEBUG side={} idx={} price={:.8} dist={:.8} qty={:.8} p_fill={:.6} edge={:.8} exit_penalty={:.8} unfilled_penalty={:.8} variance_penalty={:.8} ev={:.8}",
                    side_str,
                    idx,
                    price,
                    distance,
                    qty,
                    p_fill,
                    edge,
                    exit_penalty,
                    unfilled_penalty,
                    variance_penalty,
                    expected_value
                );
                if expected_value <= 0.0 {
                    continue;
                }

                orders.push(GridLevel {
                    side,
                    price,
                    quantity: qty,
                    distance,
                    edge,
                    p_fill,
                });
                if orders.len() >= self.config.msg_rate_budget {
                    break;
                }
            }
            if orders.len() >= self.config.msg_rate_budget {
                break;
            }
        }

        GridPlan::new(center, delta, delta_eff, target_inventory, orders)
    }
}

fn base_delta(
    params: &GridParams,
    sigma_px: f64,
    tick_size: f64,
    fee_buffer_px: f64,
    tau_fill_s: f64,
) -> f64 {
    let sigma_term = params.k_sigma * sigma_px * tau_fill_s.max(0.0).sqrt();
    let raw = sigma_term + params.k_s * tick_size + params.k_f * fee_buffer_px;
    round_to_tick(raw.max(tick_size), tick_size)
}

fn target_inventory(alpha_bps: f64, sigma_px: f64, tau_s: f64, params: &InventoryParams) -> f64 {
    if sigma_px <= 0.0 || tau_s <= 0.0 {
        return 0.0;
    }
    let denom = params.gamma * (sigma_px * sigma_px * tau_s);
    let target = params.kappa_alpha * alpha_bps / denom;
    clip(target, -params.i_max, params.i_max)
}

fn compute_center(
    microprice: f64,
    current_inventory: f64,
    target_inventory: f64,
    delta: f64,
    alpha_bps: f64,
    params: &InventoryParams,
) -> f64 {
    let inv_term = params.beta_i * (current_inventory - target_inventory) / params.i_max.max(1e-9);
    let alpha_term = params.theta_i * alpha_bps / 10_000.0;
    let skew = -inv_term + alpha_term;
    microprice + skew * delta
}

fn level_quantity(
    level_index: usize,
    params: &InventoryParams,
    current_inventory: f64,
    target_inventory: f64,
    side: OrderSide,
) -> f64 {
    let base_qty = params.base_qty.max(1e-9);
    let q = base_qty * params.eta.powi(level_index as i32);
    let inv_skew = params.theta_i * (current_inventory - target_inventory) / params.i_max.max(1e-9);
    let adjust = match side {
        OrderSide::Buy => 1.0 - inv_skew,
        OrderSide::Sell => 1.0 + inv_skew,
        OrderSide::NoOrderSide => 1.0,
    };
    let min_scale = params.q_min / base_qty;
    let max_scale = params.q_max / base_qty;
    let qty = q * clip(adjust, min_scale, max_scale);
    clip(qty, params.q_min, params.q_max)
}

fn queue_ahead(book: &OrderBook, side: OrderSide, price: f64) -> f64 {
    const EPS: f64 = 1e-9;
    match side {
        OrderSide::Buy => book
            .bids(None)
            .take_while(|level| level.price.value.as_f64() >= price - EPS)
            .map(|level| level.size())
            .sum(),
        OrderSide::Sell => book
            .asks(None)
            .take_while(|level| level.price.value.as_f64() <= price + EPS)
            .map(|level| level.size())
            .sum(),
        OrderSide::NoOrderSide => 0.0,
    }
}

fn clip(value: f64, lo: f64, hi: f64) -> f64 {
    value.max(lo).min(hi)
}

fn round_to_tick(price: f64, tick_size: f64) -> f64 {
    if tick_size <= 0.0 {
        return price;
    }
    (price / tick_size).round() * tick_size
}
