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
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! PyO3 bindings for ExecPolicy diffing (submit/cancel actions).

use crate::exec::{
    ActiveOrder as CoreActiveOrder, CancelReq as CoreCancelReq, ExecPolicy as CoreExecPolicy,
    ExecPolicyConfig as CoreExecPolicyConfig, ExecutionActions as CoreExecutionActions,
    OrderIntent as CoreOrderIntent, OrderKind as CoreOrderKind, PlannedOrder as CorePlannedOrder,
};
use nautilus_model::enums::{OrderSide, TimeInForce};
use pyo3::prelude::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora", eq)]
pub enum OrderKind {
    GRID,
    ACTIVE,
}

impl From<OrderKind> for CoreOrderKind {
    fn from(value: OrderKind) -> Self {
        match value {
            OrderKind::GRID => CoreOrderKind::Grid,
            OrderKind::ACTIVE => CoreOrderKind::Active,
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct ExecPolicyConfig {
    #[pyo3(get)]
    tick_size: f64,
    #[pyo3(get)]
    size_increment: f64,
    #[pyo3(get)]
    min_notional: f64,
    #[pyo3(get)]
    ttl_ns: i64,
    #[pyo3(get)]
    reanchor_eps_ticks: i64,
    #[pyo3(get)]
    max_changes_per_cycle: usize,
    #[pyo3(get)]
    price_eps_ticks: i64,
    #[pyo3(get)]
    qty_eps: f64,
}

#[pymethods]
impl ExecPolicyConfig {
    #[new]
    #[pyo3(
        signature = (
            tick_size=0.0,
            size_increment=0.0,
            min_notional=0.0,
            ttl_ns=0,
            reanchor_eps_ticks=0,
            max_changes_per_cycle=9223372036854775807,
            price_eps_ticks=0,
            qty_eps=0.0
        )
    )]
    pub fn new(
        tick_size: f64,
        size_increment: f64,
        min_notional: f64,
        ttl_ns: i64,
        reanchor_eps_ticks: i64,
        max_changes_per_cycle: usize,
        price_eps_ticks: i64,
        qty_eps: f64,
    ) -> Self {
        Self {
            tick_size,
            size_increment,
            min_notional,
            ttl_ns,
            reanchor_eps_ticks,
            max_changes_per_cycle,
            price_eps_ticks,
            qty_eps,
        }
    }
}

impl From<&ExecPolicyConfig> for CoreExecPolicyConfig {
    fn from(value: &ExecPolicyConfig) -> Self {
        Self {
            tick_size: value.tick_size.max(0.0),
            size_increment: value.size_increment.max(0.0),
            min_notional: value.min_notional.max(0.0),
            ttl_ns: value.ttl_ns.max(0),
            reanchor_eps_ticks: value.reanchor_eps_ticks.max(0),
            max_changes_per_cycle: value.max_changes_per_cycle.max(1),
            price_eps_ticks: value.price_eps_ticks.max(0),
            qty_eps: value.qty_eps.max(0.0),
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct ActiveOrder {
    #[pyo3(get)]
    client_order_id: Option<String>,
    #[pyo3(get)]
    side: OrderSide,
    #[pyo3(get)]
    price: f64,
    #[pyo3(get)]
    qty: f64,
    #[pyo3(get)]
    ts_placed_ns: i64,
    #[pyo3(get)]
    kind: OrderKind,
}

#[pymethods]
impl ActiveOrder {
    #[new]
    pub fn new(
        client_order_id: Option<String>,
        side: OrderSide,
        price: f64,
        qty: f64,
        ts_placed_ns: i64,
        kind: OrderKind,
    ) -> Self {
        Self {
            client_order_id,
            side,
            price,
            qty,
            ts_placed_ns,
            kind,
        }
    }
}

impl From<&ActiveOrder> for CoreActiveOrder {
    fn from(value: &ActiveOrder) -> Self {
        Self {
            client_order_id: value.client_order_id.clone(),
            side: value.side,
            price: value.price,
            qty: value.qty,
            ts_placed_ns: value.ts_placed_ns,
            kind: value.kind.into(),
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct PlannedOrder {
    #[pyo3(get)]
    side: OrderSide,
    #[pyo3(get)]
    price: f64,
    #[pyo3(get)]
    qty: f64,
    #[pyo3(get)]
    kind: OrderKind,
}

#[pymethods]
impl PlannedOrder {
    #[new]
    pub fn new(side: OrderSide, price: f64, qty: f64, kind: OrderKind) -> Self {
        Self {
            side,
            price,
            qty,
            kind,
        }
    }
}

impl From<&PlannedOrder> for CorePlannedOrder {
    fn from(value: &PlannedOrder) -> Self {
        Self {
            side: value.side,
            price: value.price,
            qty: value.qty,
            kind: value.kind.into(),
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct OrderIntent {
    #[pyo3(get)]
    side: OrderSide,
    #[pyo3(get)]
    price: f64,
    #[pyo3(get)]
    qty: f64,
    #[pyo3(get)]
    post_only: bool,
    #[pyo3(get)]
    kind: OrderKind,
    #[pyo3(get)]
    tif: Option<TimeInForce>,
}

impl From<&CoreOrderIntent> for OrderIntent {
    fn from(value: &CoreOrderIntent) -> Self {
        Self {
            side: value.side,
            price: value.price,
            qty: value.qty,
            post_only: value.post_only,
            kind: match value.kind {
                CoreOrderKind::Grid => OrderKind::GRID,
                CoreOrderKind::Active => OrderKind::ACTIVE,
            },
            tif: None, // not currently set by policy; left for future use
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct CancelReq {
    #[pyo3(get)]
    client_order_id: Option<String>,
    #[pyo3(get)]
    side: OrderSide,
    #[pyo3(get)]
    price: f64,
}

impl From<&CoreCancelReq> for CancelReq {
    fn from(value: &CoreCancelReq) -> Self {
        Self {
            client_order_id: value.client_order_id.clone(),
            side: value.side,
            price: value.price,
        }
    }
}

#[derive(Clone, Debug)]
#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct ExecutionActions {
    #[pyo3(get)]
    submit: Vec<OrderIntent>,
    #[pyo3(get)]
    cancel: Vec<CancelReq>,
}

impl From<CoreExecutionActions> for ExecutionActions {
    fn from(value: CoreExecutionActions) -> Self {
        Self {
            submit: value.submit.iter().map(OrderIntent::from).collect(),
            cancel: value.cancel.iter().map(CancelReq::from).collect(),
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct ExecPolicy {
    pub(crate) inner: CoreExecPolicy,
}

#[pymethods]
impl ExecPolicy {
    #[new]
    pub fn new(cfg: ExecPolicyConfig) -> Self {
        Self {
            inner: CoreExecPolicy::new((&cfg).into()),
        }
    }

    pub fn diff(
        &self,
        active_orders: Vec<ActiveOrder>,
        planned_orders: Vec<PlannedOrder>,
        ts_now: i64,
        center: Option<f64>,
    ) -> ExecutionActions {
        let active: Vec<CoreActiveOrder> =
            active_orders.iter().map(CoreActiveOrder::from).collect();
        let planned: Vec<CorePlannedOrder> =
            planned_orders.iter().map(CorePlannedOrder::from).collect();
        self.inner.diff(&active, &planned, ts_now, center).into()
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<OrderKind>()?;
    m.add_class::<ExecPolicyConfig>()?;
    m.add_class::<ActiveOrder>()?;
    m.add_class::<PlannedOrder>()?;
    m.add_class::<OrderIntent>()?;
    m.add_class::<CancelReq>()?;
    m.add_class::<ExecutionActions>()?;
    m.add_class::<ExecPolicy>()?;
    Ok(())
}
