// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
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

use std::fmt::Display;

use nautilus_model::orderbook::OrderBook;

use crate::aurora_indicators::ValueIndicator;
use crate::indicator::Indicator;

#[repr(C)]
#[derive(Debug, Default)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(module = "nautilus_trader.core.nautilus_pyo3.indicators")
)]
pub struct ImbalanceFactor {
    value: f64,
    count: usize,
    initialized: bool,
    has_inputs: bool,
}

impl Display for ImbalanceFactor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for ImbalanceFactor {
    fn name(&self) -> String {
        stringify!(ImbalanceFactor).to_string()
    }

    fn has_inputs(&self) -> bool {
        self.has_inputs
    }

    fn initialized(&self) -> bool {
        self.initialized
    }

    fn handle_book(&mut self, book: &OrderBook) {
        let bid_qty = book.best_bid_size().map(|q| q.as_f64());
        let ask_qty = book.best_ask_size().map(|q| q.as_f64());
        self.update(bid_qty, ask_qty);
    }

    fn reset(&mut self) {
        *self = Self::default();
    }
}

impl ImbalanceFactor {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            value: 0.0,
            count: 0,
            initialized: false,
            has_inputs: false,
        }
    }

    pub fn update(&mut self, bid_qty: Option<f64>, ask_qty: Option<f64>) {
        self.has_inputs = true;
        self.count += 1;

        if let (Some(bq), Some(aq)) = (bid_qty, ask_qty) {
            let total = bq + aq;
            if total > f64::EPSILON {
                self.value = (bq - aq) / total;
            } else {
                self.value = 0.0;
            }
            self.initialized = true;
        } else {
            self.value = 0.0;
            self.initialized = false;
        }
    }
}

impl ValueIndicator for ImbalanceFactor {
    fn value(&self) -> f64 {
        self.value
    }
}
