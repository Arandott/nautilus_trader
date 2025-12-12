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

//! PyO3 bindings for the Aurora orchestrator (single-book, queue-stats driven).

use crate::alpha::RlsAlpha as CoreRlsAlpha;
use crate::orchestrator::{AuroraOrchestrator as CoreOrchestrator, OrchestratorConfig as CoreOrchestratorConfig};
use crate::ActiveOrder as CoreActiveOrder;
use nautilus_core::python::to_pyvalue_err;
use nautilus_model::{
    data::{OrderBookDeltas, TradeTick},
    enums::BookType,
    identifiers::InstrumentId,
};
use pyo3::prelude::*;

use super::alpha::{AlphaEngineParams, RlsAlpha, build_rls_engine};
use super::exec::{ActiveOrder, ExecPolicy, ExecutionActions};
use super::grid::AuroraGridPlanner;
use super::risk::AuroraRiskAdvisor;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct OrchestratorConfig {
    #[pyo3(get)]
    instrument_id: InstrumentId,
    #[pyo3(get)]
    book_type: BookType,
    #[pyo3(get)]
    queue_window_ms: f64,
    #[pyo3(get)]
    tick_size: f64,
    #[pyo3(get)]
    base_sigma: f64,
    #[pyo3(get)]
    tau_alpha_s: f64,
    #[pyo3(get)]
    tau_fill_s: f64,
}

#[pymethods]
impl OrchestratorConfig {
    #[new]
    #[pyo3(
        signature = (
            instrument_id,
            book_type = BookType::L2_MBP,
            queue_window_ms = 300.0,
            tick_size = 0.0,
            base_sigma = 1e-6,
            tau_alpha_s = 0.3,
            tau_fill_s = 0.3
        )
    )]
    pub fn new(
        instrument_id: InstrumentId,
        book_type: BookType,
        queue_window_ms: f64,
        tick_size: f64,
        base_sigma: f64,
        tau_alpha_s: f64,
        tau_fill_s: f64,
    ) -> Self {
        Self {
            instrument_id,
            book_type,
            queue_window_ms,
            tick_size,
            base_sigma,
            tau_alpha_s,
            tau_fill_s,
        }
    }
}

impl From<&OrchestratorConfig> for CoreOrchestratorConfig {
    fn from(value: &OrchestratorConfig) -> Self {
        Self {
            instrument_id: value.instrument_id,
            book_type: value.book_type,
            queue_window_ms: value.queue_window_ms,
            tick_size: value.tick_size,
            base_sigma: value.base_sigma,
            tau_alpha_s: value.tau_alpha_s,
            tau_fill_s: value.tau_fill_s,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraOrchestrator {
    inner: CoreOrchestrator<CoreRlsAlpha>,
}

#[pymethods]
impl AuroraOrchestrator {
    #[new]
    #[pyo3(signature = (config, model, grid_planner, risk_advisor, exec_policy, alpha_params=None))]
    pub fn new(
        config: OrchestratorConfig,
        model: Py<RlsAlpha>,
        grid_planner: AuroraGridPlanner,
        risk_advisor: AuroraRiskAdvisor,
        exec_policy: ExecPolicy,
        alpha_params: Option<AlphaEngineParams>,
    ) -> PyResult<Self> {
        let params = alpha_params.unwrap_or_default();
        let alpha = build_rls_engine(&model, &params)?;
        let cfg: CoreOrchestratorConfig = (&config).into();
        let inner = CoreOrchestrator::new(
            cfg,
            alpha,
            risk_advisor.inner.clone(),
            grid_planner.inner.clone(),
            exec_policy.inner.clone(),
        )
        .map_err(to_pyvalue_err)?;
        Ok(Self { inner })
    }

    pub fn set_inventory(&mut self, qty: f64) {
        self.inner.set_inventory(qty);
    }

    pub fn handle_orderbook(
        &mut self,
        deltas: &OrderBookDeltas,
        active_orders: Vec<ActiveOrder>,
        inventory_qty: f64,
        ts_ns: Option<i64>,
    ) -> PyResult<ExecutionActions> {
        let ts = ts_ns.unwrap_or_else(|| deltas.ts_event.as_i64());
        let active: Vec<CoreActiveOrder> =
            active_orders.iter().map(CoreActiveOrder::from).collect();
        let actions = self
            .inner
            .handle_orderbook(ts, deltas, &active, inventory_qty)
            .map_err(to_pyvalue_err)?;
        Ok(actions.into())
    }

    pub fn handle_trade(
        &mut self,
        trade: &TradeTick,
        ts_ns: Option<i64>,
    ) -> PyResult<ExecutionActions> {
        let ts = ts_ns.unwrap_or_else(|| trade.ts_event.as_i64());
        let actions = self
            .inner
            .handle_trade(ts, trade)
            .map_err(to_pyvalue_err)?;
        Ok(actions.into())
    }
}

pub fn register(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<OrchestratorConfig>()?;
    m.add_class::<AuroraOrchestrator>()?;
    Ok(())
}
