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

//! PyO3 bindings for the Aurora alpha models.

use crate::alpha::{RlsAlpha as CoreRlsAlpha, RlsParams as CoreRlsParams};
use pyo3::prelude::*;

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct RlsParams {
    #[pyo3(get)]
    forgetting: f64,
    #[pyo3(get)]
    ridge: f64,
    #[pyo3(get)]
    a_max_bps: f64,
}

impl From<&RlsParams> for CoreRlsParams {
    fn from(value: &RlsParams) -> Self {
        Self {
            forgetting: value.forgetting,
            ridge: value.ridge,
            a_max_bps: value.a_max_bps,
        }
    }
}

#[pymethods]
impl RlsParams {
    #[new]
    #[pyo3(signature = (forgetting=0.995, ridge=1.0, a_max_bps=3.0))]
    pub fn new(forgetting: f64, ridge: f64, a_max_bps: f64) -> Self {
        Self {
            forgetting,
            ridge,
            a_max_bps,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct RlsAlpha {
    inner: CoreRlsAlpha,
}

#[pymethods]
impl RlsAlpha {
    #[new]
    pub fn new(dimension: usize, params: Option<RlsParams>) -> Self {
        let core_params = params.as_ref().map(CoreRlsParams::from).unwrap_or_default();
        Self {
            inner: CoreRlsAlpha::new(dimension, core_params),
        }
    }

    pub fn predict(&self, features: Vec<f64>) -> f64 {
        self.inner.predict(&features)
    }

    pub fn update(&mut self, features: Vec<f64>, target_bps: f64) {
        self.inner.update(&features, target_bps);
    }

    pub fn weights(&self) -> Vec<f64> {
        self.inner.weights().to_vec()
    }

    #[getter]
    pub fn dimension(&self) -> usize {
        self.inner.dimension()
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RlsParams>()?;
    m.add_class::<RlsAlpha>()?;
    Ok(())
}
