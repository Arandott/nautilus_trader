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

use crate::alpha::{
    AlphaEngine as CoreAlphaEngine, AlphaModel, RlsAlpha as CoreRlsAlpha,
    RlsParams as CoreRlsParams,
};
use nautilus_core::python::to_pyvalue_err;
use nautilus_model::{
    data::{OrderBookDeltas, TradeTick},
    enums::BookType,
    identifiers::InstrumentId,
};
use pyo3::{exceptions::PyTypeError, prelude::*, Py};
type CoreRlsEngine = CoreAlphaEngine<CoreRlsAlpha>;
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
    pub fn new(dimension: usize, params: Option<RlsParams>) -> PyResult<Self> {
        let core_params = params.as_ref().map(CoreRlsParams::from).unwrap_or_default();
        let model = CoreRlsAlpha::new(dimension, core_params).map_err(to_pyvalue_err)?;
        Ok(Self { inner: model })
    }

    pub fn predict(&self, features: Vec<f64>) -> PyResult<f64> {
        self.inner.predict(&features).map_err(to_pyvalue_err)
    }

    pub fn update(&mut self, features: Vec<f64>, target_bps: f64) -> PyResult<()> {
        self.inner
            .update(&features, target_bps)
            .map_err(to_pyvalue_err)
    }

    pub fn weights(&self) -> Vec<f64> {
        self.inner.weights().to_vec()
    }

    #[getter]
    pub fn dimension(&self) -> usize {
        self.inner.dimension()
    }
}

#[derive(Debug)]
enum EngineVariant {
    Rls(CoreRlsEngine),
}

enum PyAlphaModel {
    Rls(Py<RlsAlpha>),
}

impl<'py> FromPyObject<'py> for PyAlphaModel {
    fn extract_bound(obj: &Bound<'py, PyAny>) -> PyResult<Self> {
        if let Ok(model) = obj.extract::<Py<RlsAlpha>>() {
            return Ok(Self::Rls(model));
        }
        Err(PyTypeError::new_err(
            "unsupported alpha model; expected RlsAlpha",
        ))
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Clone, Debug)]
pub struct AlphaEngineParams {
    #[pyo3(get)]
    lag_ns: i64,
    #[pyo3(get)]
    tick_size: f64,
    #[pyo3(get)]
    i_max: f64,
    #[pyo3(get)]
    time_stride_ns: i64,
    #[pyo3(get)]
    count_stride: usize,
    #[pyo3(get)]
    min_updates_for_output: usize,
    #[pyo3(get)]
    label_queue_len: usize,
    #[pyo3(get)]
    base_sigma: f64,
    #[pyo3(get)]
    features: Option<Vec<String>>,
}

impl Default for AlphaEngineParams {
    fn default() -> Self {
        Self {
            lag_ns: 300_000_000,
            tick_size: 0.0,
            i_max: 1.0,
            time_stride_ns: 20_000_000,
            count_stride: 1,
            min_updates_for_output: 0,
            label_queue_len: 2048,
            base_sigma: 1e-6,
            features: None,
        }
    }
}

#[pymethods]
impl AlphaEngineParams {
    #[new]
    #[pyo3(
        signature = (
            lag_ns=300_000_000,
            tick_size=0.0,
            i_max=1.0,
            time_stride_ns=20_000_000,
            count_stride=1,
            min_updates_for_output=0,
            label_queue_len=2048,
            base_sigma=1e-6,
            features=None
        )
    )]
    pub fn new(
        lag_ns: i64,
        tick_size: f64,
        i_max: f64,
        time_stride_ns: i64,
        count_stride: usize,
        min_updates_for_output: usize,
        label_queue_len: usize,
        base_sigma: f64,
        features: Option<Vec<String>>,
    ) -> Self {
        Self {
            lag_ns,
            tick_size,
            i_max,
            time_stride_ns,
            count_stride,
            min_updates_for_output,
            label_queue_len,
            base_sigma,
            features,
        }
    }
}

#[pyclass(module = "nautilus_trader.core.nautilus_pyo3.aurora")]
#[derive(Debug)]
pub struct AlphaEngine {
    inner: EngineVariant,
}

#[pymethods]
impl AlphaEngine {
    #[new]
    #[pyo3(signature = (model, instrument_id, book_type, params=None))]
    pub fn new(
        model: PyAlphaModel,
        instrument_id: InstrumentId,
        book_type: BookType,
        params: Option<AlphaEngineParams>,
    ) -> PyResult<Self> {
        let params = params.unwrap_or_default();
        let feature_names = parse_features(params.features.as_ref());
        let inner = match model {
            PyAlphaModel::Rls(py_model) => {
                let core_model = Python::with_gil(|py| py_model.borrow(py).inner.clone());
                CoreRlsEngine::new_with_model(
                    instrument_id,
                    book_type,
                    params.lag_ns,
                    params.tick_size,
                    params.i_max,
                    core_model,
                    params.time_stride_ns,
                    params.count_stride,
                    params.min_updates_for_output,
                    params.label_queue_len,
                    params.base_sigma,
                    feature_names,
                )
                .map(EngineVariant::Rls)
            }
        }
        .map_err(to_pyvalue_err)?;
        Ok(Self { inner })
    }

    pub fn handle_order_book(
        &mut self,
        ts_ns: i64,
        deltas: &OrderBookDeltas,
        inventory_qty: f64,
    ) -> PyResult<f64> {
        match &mut self.inner {
            EngineVariant::Rls(engine) => engine.handle_order_book(ts_ns, deltas, inventory_qty),
        }
        .map_err(to_pyvalue_err)
    }

    pub fn handle_trade(&mut self, ts_ns: i64, trade: &TradeTick) -> PyResult<Option<f64>> {
        match &mut self.inner {
            EngineVariant::Rls(engine) => engine.handle_trade(ts_ns, trade),
        }
        .map_err(to_pyvalue_err)
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RlsParams>()?;
    m.add_class::<RlsAlpha>()?;
    m.add_class::<AlphaEngineParams>()?;
    m.add_class::<AlphaEngine>()?;
    Ok(())
}

fn parse_features(feature_names: Option<&Vec<String>>) -> Option<Vec<String>> {
    feature_names.filter(|names| !names.is_empty()).cloned()
}
