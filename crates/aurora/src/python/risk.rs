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

//! PyO3 bindings for Aurora risk advisory helpers.

use crate::risk::{RiskAdvisor as CoreRiskAdvisor, RiskDecision as CoreRiskDecision, RiskState};
use pyo3::prelude::*;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuroraRiskState {
    NORMAL,
    WIDEN,
    PAUSE,
}

impl From<RiskState> for AuroraRiskState {
    fn from(value: RiskState) -> Self {
        match value {
            RiskState::Normal => Self::NORMAL,
            RiskState::Widen => Self::WIDEN,
            RiskState::Pause => Self::PAUSE,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraRiskDecision {
    #[pyo3(get)]
    state: AuroraRiskState,
    #[pyo3(get)]
    widen_factor: f64,
    #[pyo3(get)]
    reduce_levels: u32,
    #[pyo3(get)]
    hedge_qty: f64,
    #[pyo3(get)]
    reason: Option<String>,
}

impl From<CoreRiskDecision> for AuroraRiskDecision {
    fn from(value: CoreRiskDecision) -> Self {
        Self {
            state: value.state.into(),
            widen_factor: value.widen_factor,
            reduce_levels: value.reduce_levels,
            hedge_qty: value.hedge_qty,
            reason: value.reason,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
pub struct AuroraRiskAdvisor {
    inner: CoreRiskAdvisor,
}

#[pymethods]
impl AuroraRiskAdvisor {
    #[new]
    pub fn new(
        vol_shock_sigma_mult: f64,
        inventory_soft_limit: f64,
        hedge_cooldown_ms: f64,
        hedge_min_qty: f64,
    ) -> Self {
        Self {
            inner: CoreRiskAdvisor::new(
                vol_shock_sigma_mult,
                inventory_soft_limit,
                hedge_cooldown_ms,
                hedge_min_qty,
            ),
        }
    }

    pub fn advise(
        &mut self,
        sigma_rel: f64,
        base_sigma: f64,
        inventory_qty: f64,
        now_ns: u64,
    ) -> AuroraRiskDecision {
        self.inner
            .advise(sigma_rel, base_sigma, inventory_qty, now_ns)
            .into()
    }
}

pub fn register(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<AuroraRiskAdvisor>()?;
    m.add_class::<AuroraRiskDecision>()?;
    m.add_class::<AuroraRiskState>()?;
    Ok(())
}
