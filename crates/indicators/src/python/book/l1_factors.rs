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

use crate::{book::l1_factors::BookL1Factors, indicator::Indicator};

#[pymethods]
impl BookL1Factors {
    #[new]
    const fn py_new() -> Self {
        Self::new()
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
    const fn py_count(&self) -> usize {
        self.count
    }

    #[getter]
    #[pyo3(name = "has_inputs")]
    fn py_has_inputs(&self) -> bool {
        self.has_inputs()
    }

    #[getter]
    #[pyo3(name = "initialized")]
    const fn py_initialized(&self) -> bool {
        self.initialized
    }

    #[getter]
    #[pyo3(name = "has_market")]
    const fn py_has_market(&self) -> bool {
        self.has_market
    }

    #[getter]
    #[pyo3(name = "bid_price")]
    fn py_bid_price(&self) -> Option<f64> {
        self.bid_price
    }

    #[getter]
    #[pyo3(name = "ask_price")]
    fn py_ask_price(&self) -> Option<f64> {
        self.ask_price
    }

    #[getter]
    #[pyo3(name = "bid_qty")]
    fn py_bid_qty(&self) -> Option<f64> {
        self.bid_qty
    }

    #[getter]
    #[pyo3(name = "ask_qty")]
    fn py_ask_qty(&self) -> Option<f64> {
        self.ask_qty
    }

    #[getter]
    #[pyo3(name = "mid")]
    fn py_mid(&self) -> Option<f64> {
        self.mid
    }

    #[getter]
    #[pyo3(name = "microprice")]
    fn py_microprice(&self) -> Option<f64> {
        self.microprice
    }

    #[getter]
    #[pyo3(name = "imbalance")]
    fn py_imbalance(&self) -> Option<f64> {
        self.imbalance
    }

    #[getter]
    #[pyo3(name = "spread")]
    fn py_spread(&self) -> Option<f64> {
        self.spread
    }

    #[pyo3(name = "handle_book")]
    fn py_handle_book(&mut self, book: &OrderBook) {
        self.handle_book(book);
    }

    #[pyo3(name = "update")]
    #[pyo3(signature = (bid_price=None, bid_qty=None, ask_price=None, ask_qty=None))]
    fn py_update(
        &mut self,
        bid_price: Option<f64>,
        bid_qty: Option<f64>,
        ask_price: Option<f64>,
        ask_qty: Option<f64>,
    ) {
        self.update(bid_price, bid_qty, ask_price, ask_qty);
    }

    #[pyo3(name = "reset")]
    fn py_reset(&mut self) {
        self.reset();
    }
}
