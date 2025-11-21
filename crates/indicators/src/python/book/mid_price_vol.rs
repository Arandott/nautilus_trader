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

use nautilus_model::orderbook::OrderBook;
use pyo3::prelude::*;

use crate::{book::mid_price_vol::BookMidPriceVolEstimator, indicator::Indicator};

#[pymethods]
impl BookMidPriceVolEstimator {
    #[new]
    #[pyo3(signature = (decay=None))]
    fn py_new(decay: Option<f64>) -> Self {
        Self::new(decay.unwrap_or(0.94))
    }

    fn __repr__(&self) -> String {
        self.to_string()
    }

    #[getter]
    #[pyo3(name = "name")]
    fn py_name(&self) -> String {
        self.name()
    }

    #[getter]
    #[pyo3(name = "count")]
    fn py_count(&self) -> usize {
        self.count()
    }

    #[getter]
    #[pyo3(name = "has_inputs")]
    fn py_has_inputs(&self) -> bool {
        self.has_inputs()
    }

    #[getter]
    #[pyo3(name = "initialized")]
    fn py_initialized(&self) -> bool {
        self.initialized()
    }

    #[getter]
    #[pyo3(name = "decay")]
    fn py_decay(&self) -> f64 {
        self.decay()
    }

    #[getter]
    #[pyo3(name = "sigma_rel")]
    fn py_sigma_rel(&self) -> f64 {
        self.sigma_rel()
    }

    #[pyo3(name = "sigma_px")]
    fn py_sigma_px(&self, mid: f64) -> f64 {
        self.sigma_px(mid)
    }

    #[pyo3(name = "update")]
    fn py_update(&mut self, mid: f64) {
        self.update(mid);
    }

    #[pyo3(name = "handle_book")]
    fn py_handle_book(&mut self, book: &OrderBook) {
        self.handle_book(book);
    }

    #[pyo3(name = "reset")]
    fn py_reset(&mut self) {
        self.reset();
    }
}
