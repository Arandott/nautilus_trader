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

//! Fill probability helpers exposed to the Aurora strategy.

use crate::fill::{FillModel as CoreFillModel, QueueStats as CoreQueueStats};
use nautilus_model::enums::OrderSide;
use pyo3::prelude::*;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct AuroraQueueStats {
    pub(super) inner: CoreQueueStats,
}

#[pymethods]
impl AuroraQueueStats {
    #[new]
    #[pyo3(
        signature = (
            lambda_mo = 0.0,
            lambda_cancel = 0.0,
            mean_mo = 0.0,
            var_mo = 0.0,
            touch_rate = 0.0
        )
    )]
    pub fn new(
        lambda_mo: f64,
        lambda_cancel: f64,
        mean_mo: f64,
        var_mo: f64,
        touch_rate: f64,
    ) -> Self {
        Self {
            inner: CoreQueueStats::new(lambda_mo, lambda_cancel, mean_mo, var_mo, touch_rate),
        }
    }

    #[getter]
    fn lambda_mo(&self) -> f64 {
        self.inner.lambda_mo()
    }

    #[setter]
    fn set_lambda_mo(&mut self, value: f64) {
        self.inner.set_lambda_mo(value);
    }

    #[getter]
    fn lambda_cancel(&self) -> f64 {
        self.inner.lambda_cancel()
    }

    #[setter]
    fn set_lambda_cancel(&mut self, value: f64) {
        self.inner.set_lambda_cancel(value);
    }

    #[getter]
    fn mean_mo(&self) -> f64 {
        self.inner.mean_mo()
    }

    #[setter]
    fn set_mean_mo(&mut self, value: f64) {
        self.inner.set_mean_mo(value);
    }

    #[getter]
    fn var_mo(&self) -> f64 {
        self.inner.var_mo()
    }

    #[setter]
    fn set_var_mo(&mut self, value: f64) {
        self.inner.set_var_mo(value);
    }

    #[getter]
    fn touch_rate(&self) -> f64 {
        self.inner.touch_rate()
    }

    #[setter]
    fn set_touch_rate(&mut self, value: f64) {
        self.inner.set_touch_rate(value);
    }

    pub fn update(&mut self, mo_rate: f64, cxl_rate: f64, mean_mo: f64, var_mo: f64, decay: f64) {
        self.inner.update(mo_rate, cxl_rate, mean_mo, var_mo, decay);
    }

    pub fn update_touch(&mut self, hit: bool, dt_s: f64, decay: f64) {
        self.inner.update_touch(hit, dt_s, decay);
    }
}

impl AuroraQueueStats {
    pub(crate) fn inner(&self) -> &CoreQueueStats {
        &self.inner
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct AuroraFillModel {
    inner: CoreFillModel,
}

#[pymethods]
impl AuroraFillModel {
    #[new]
    #[pyo3(signature = (min_p = 0.05, tick_size = 0.01, use_empirical_touch = false))]
    pub fn new(min_p: f64, tick_size: f64, use_empirical_touch: bool) -> Self {
        Self {
            inner: CoreFillModel::new(min_p, tick_size, use_empirical_touch),
        }
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (side, distance, mu, sigma_px, horizon_s, stats=None))]
    pub fn p_touch(
        &self,
        side: OrderSide,
        distance: f64,
        mu: f64,
        sigma_px: f64,
        horizon_s: f64,
        stats: Option<&AuroraQueueStats>,
    ) -> f64 {
        self.inner
            .p_touch(side, distance, mu, sigma_px, horizon_s, stats.map(|s| s.inner()))
    }

    pub fn p_queue(&self, queue_ahead: f64, stats: &AuroraQueueStats, horizon_s: f64) -> f64 {
        self.inner.p_queue(queue_ahead, stats.inner(), horizon_s)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn p_fill(
        &self,
        side: OrderSide,
        distance: f64,
        mu: f64,
        sigma_px: f64,
        horizon_s: f64,
        queue_ahead: f64,
        stats: &AuroraQueueStats,
    ) -> f64 {
        self.inner
            .p_fill(side, distance, mu, sigma_px, horizon_s, queue_ahead, stats.inner())
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<AuroraQueueStats>()?;
    m.add_class::<AuroraFillModel>()?;
    Ok(())
}
