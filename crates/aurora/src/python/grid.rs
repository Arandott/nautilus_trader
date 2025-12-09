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

//! PyO3 bindings for Aurora grid planning primitives.

use crate::{
    fill::FillModel as CoreFillModel,
    grid::{
        GridLevel as CoreGridLevel, GridParams as CoreGridParams, GridPlan as CoreGridPlan,
        GridPlanner as CoreGridPlanner, GridPlannerConfig, InventoryParams as CoreInventoryParams,
    },
};
use nautilus_model::{enums::OrderSide, orderbook::OrderBook};
use pyo3::prelude::*;

use super::fill::AuroraQueueStats;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct GridLevel {
    #[pyo3(get)]
    side: OrderSide,
    #[pyo3(get)]
    price: f64,
    #[pyo3(get)]
    quantity: f64,
    #[pyo3(get)]
    distance: f64,
    #[pyo3(get)]
    edge: f64,
    #[pyo3(get)]
    p_fill: f64,
}

impl From<&CoreGridLevel> for GridLevel {
    fn from(value: &CoreGridLevel) -> Self {
        Self {
            side: value.side,
            price: value.price,
            quantity: value.quantity,
            distance: value.distance,
            edge: value.edge,
            p_fill: value.p_fill,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct GridPlan {
    inner: CoreGridPlan,
}

#[pymethods]
impl GridPlan {
    #[getter]
    fn center(&self) -> f64 {
        self.inner.center()
    }

    #[getter]
    fn delta(&self) -> f64 {
        self.inner.delta()
    }

    #[getter]
    fn delta_eff(&self) -> f64 {
        self.inner.delta_eff()
    }

    #[getter]
    fn target_inventory(&self) -> f64 {
        self.inner.target_inventory()
    }

    fn orders(&self) -> Vec<GridLevel> {
        self.inner.orders().iter().map(GridLevel::from).collect()
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraGridPlanner {
    inner: CoreGridPlanner,
}

#[pymethods]
impl AuroraGridPlanner {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(
        signature = (
            grid_levels,
            k_sigma,
            k_s,
            k_f,
            fee_buffer_bps,
            delta_entry_ticks,
            exit_cost_bps,
            q_mm,
            unfilled_penalty_ticks,
            i_max,
            i_soft,
            gamma,
            kappa_alpha,
            beta_i,
            theta_i,
            base_qty,
            eta,
            q_min,
            q_max,
            msg_rate_budget,
            tick_size,
            min_p_fill,
            use_empirical_touch
        )
    )]
    pub fn new(
        grid_levels: usize,
        k_sigma: f64,
        k_s: f64,
        k_f: f64,
        fee_buffer_bps: f64,
        delta_entry_ticks: f64,
        exit_cost_bps: f64,
        q_mm: f64,
        unfilled_penalty_ticks: f64,
        i_max: f64,
        i_soft: f64,
        gamma: f64,
        kappa_alpha: f64,
        beta_i: f64,
        theta_i: f64,
        base_qty: f64,
        eta: f64,
        q_min: f64,
        q_max: f64,
        msg_rate_budget: usize,
        tick_size: f64,
        min_p_fill: f64,
        use_empirical_touch: bool,
    ) -> Self {
        let config = GridPlannerConfig {
            grid: CoreGridParams {
                levels: grid_levels,
                k_sigma,
                k_s,
                k_f,
                fee_buffer_bps,
                delta_entry_ticks,
                exit_cost_bps,
                q_mm,
                unfilled_penalty_ticks,
            },
            inventory: CoreInventoryParams {
                i_max,
                i_soft,
                gamma,
                kappa_alpha,
                beta_i,
                theta_i,
                base_qty,
                eta,
                q_min,
                q_max,
            },
            msg_rate_budget: msg_rate_budget.max(1),
            tick_size: tick_size.max(1e-9),
        };
        let fill_model = CoreFillModel::new(min_p_fill, tick_size, use_empirical_touch);
        Self {
            inner: CoreGridPlanner::new(config, fill_model),
        }
    }

    #[allow(clippy::too_many_arguments)]
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
        bid_stats: &AuroraQueueStats,
        ask_stats: &AuroraQueueStats,
    ) -> GridPlan {
        let plan = self.inner.plan(
            book,
            mid,
            microprice,
            sigma_px,
            alpha_bps,
            tau_alpha_s,
            tau_fill_s,
            inventory_qty,
            widen_factor,
            reduce_levels,
            bid_stats.inner(),
            ask_stats.inner(),
        );
        GridPlan { inner: plan }
    }
}

pub fn register(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GridLevel>()?;
    m.add_class::<GridPlan>()?;
    m.add_class::<AuroraGridPlanner>()?;
    Ok(())
}
