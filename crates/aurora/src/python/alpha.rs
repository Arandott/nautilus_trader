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
    AlphaEngine as CoreAlphaEngine, AlphaModel, PredictPolicyConfig, RlsAlpha as CoreRlsAlpha,
    RlsParams as CoreRlsParams, TriggerLogic, UpdatePolicyConfig,
};
use nautilus_core::python::to_pyvalue_err;
use nautilus_model::{data::TradeTick, enums::BookType, identifiers::InstrumentId, orderbook::OrderBook};
use pyo3::prelude::*;
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
    #[pyo3(get)]
    predict_mid_move_bps: Option<f64>,
    #[pyo3(get)]
    predict_sigma_jump: Option<f64>,
    #[pyo3(get)]
    predict_inventory_delta: Option<f64>,
    #[pyo3(get)]
    predict_require_mid_valid: bool,
    #[pyo3(get)]
    predict_trigger_logic: String,
    #[pyo3(get)]
    update_min_interval_ns: i64,
    #[pyo3(get)]
    update_count_stride: usize,
    #[pyo3(get)]
    update_sample_rate: f64,
    #[pyo3(get)]
    update_label_clip_bps: Option<f64>,
    #[pyo3(get)]
    update_label_min_abs_bps: Option<f64>,
    #[pyo3(get)]
    update_mid_required: bool,
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
            predict_mid_move_bps: None,
            predict_sigma_jump: None,
            predict_inventory_delta: None,
            predict_require_mid_valid: true,
            predict_trigger_logic: "any".to_string(),
            update_min_interval_ns: 0,
            update_count_stride: 1,
            update_sample_rate: 1.0,
            update_label_clip_bps: None,
            update_label_min_abs_bps: None,
            update_mid_required: true,
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
            features=None,
            predict_mid_move_bps=None,
            predict_sigma_jump=None,
            predict_inventory_delta=None,
            predict_require_mid_valid=true,
            predict_trigger_logic="any",
            update_min_interval_ns=0,
            update_count_stride=1,
            update_sample_rate=1.0,
            update_label_clip_bps=None,
            update_label_min_abs_bps=None,
            update_mid_required=true
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
        predict_mid_move_bps: Option<f64>,
        predict_sigma_jump: Option<f64>,
        predict_inventory_delta: Option<f64>,
        predict_require_mid_valid: bool,
        predict_trigger_logic: &str,
        update_min_interval_ns: i64,
        update_count_stride: usize,
        update_sample_rate: f64,
        update_label_clip_bps: Option<f64>,
        update_label_min_abs_bps: Option<f64>,
        update_mid_required: bool,
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
            predict_mid_move_bps,
            predict_sigma_jump,
            predict_inventory_delta,
            predict_require_mid_valid,
            predict_trigger_logic: predict_trigger_logic.to_string(),
            update_min_interval_ns,
            update_count_stride,
            update_sample_rate,
            update_label_clip_bps,
            update_label_min_abs_bps,
            update_mid_required,
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
    #[pyo3(signature = (model, _instrument_id, _book_type, params=None))]
    pub fn new(
        model: Py<RlsAlpha>,
        _instrument_id: InstrumentId,
        _book_type: BookType,
        params: Option<AlphaEngineParams>,
    ) -> PyResult<Self> {
        let params = params.unwrap_or_default();
        let feature_names = parse_features(params.features.as_ref());
        let predict_cfg = PredictPolicyConfig {
            mid_move_bps: params.predict_mid_move_bps,
            sigma_jump: params.predict_sigma_jump,
            inventory_delta: params.predict_inventory_delta,
            require_mid_valid: params.predict_require_mid_valid,
            trigger_logic: match params.predict_trigger_logic.to_lowercase().as_str() {
                "all" => TriggerLogic::All,
                _ => TriggerLogic::Any,
            },
        };
        let update_cfg = UpdatePolicyConfig {
            min_update_interval_ns: params.update_min_interval_ns,
            count_stride: params.update_count_stride,
            sample_rate: params.update_sample_rate,
            label_clip_bps: params.update_label_clip_bps,
            label_min_abs_bps: params.update_label_min_abs_bps,
            mid_required: params.update_mid_required,
        };
        let core_model = Python::with_gil(|py| model.borrow(py).inner.clone());
        let inner = CoreRlsEngine::new_with_model(
            params.lag_ns,
            params.tick_size,
            params.i_max,
            core_model,
            params.time_stride_ns,
            params.count_stride,
            params.min_updates_for_output,
            params.label_queue_len,
            params.base_sigma,
            predict_cfg,
            update_cfg,
            feature_names,
        )
        .map(EngineVariant::Rls)
        .map_err(to_pyvalue_err)?;
        Ok(Self { inner })
    }

    pub fn handle_order_book(
        &mut self,
        book: &OrderBook,
        ts_ns: i64,
        inventory_qty: f64,
    ) -> PyResult<f64> {
        match &mut self.inner {
            EngineVariant::Rls(engine) => engine.handle_order_book(ts_ns, book, inventory_qty),
        }
        .map_err(to_pyvalue_err)
    }

    pub fn handle_trade(
        &mut self,
        ts_ns: i64,
        trade: &TradeTick,
        book: &OrderBook,
    ) -> PyResult<Option<f64>> {
        match &mut self.inner {
            EngineVariant::Rls(engine) => engine.handle_trade(ts_ns, trade, book),
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

pub(crate) fn parse_features(feature_names: Option<&Vec<String>>) -> Option<Vec<String>> {
    feature_names.filter(|names| !names.is_empty()).cloned()
}

pub(crate) fn build_rls_engine(
    model: &Py<RlsAlpha>,
    params: &AlphaEngineParams,
) -> PyResult<CoreRlsEngine> {
    let feature_names = parse_features(params.features.as_ref());
    let predict_cfg = PredictPolicyConfig {
        mid_move_bps: params.predict_mid_move_bps,
        sigma_jump: params.predict_sigma_jump,
        inventory_delta: params.predict_inventory_delta,
        require_mid_valid: params.predict_require_mid_valid,
        trigger_logic: match params.predict_trigger_logic.to_lowercase().as_str() {
            "all" => TriggerLogic::All,
            _ => TriggerLogic::Any,
        },
    };
    let update_cfg = UpdatePolicyConfig {
        min_update_interval_ns: params.update_min_interval_ns,
        count_stride: params.update_count_stride,
        sample_rate: params.update_sample_rate,
        label_clip_bps: params.update_label_clip_bps,
        label_min_abs_bps: params.update_label_min_abs_bps,
        mid_required: params.update_mid_required,
    };
    let core_model = Python::with_gil(|py| model.borrow(py).inner.clone());
    CoreRlsEngine::new_with_model(
        params.lag_ns,
        params.tick_size,
        params.i_max,
        core_model,
        params.time_stride_ns,
        params.count_stride,
        params.min_updates_for_output,
        params.label_queue_len,
        params.base_sigma,
        predict_cfg,
        update_cfg,
        feature_names,
    )
    .map_err(to_pyvalue_err)
}
