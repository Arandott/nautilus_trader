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
pub struct MicroSkewFactor {
    tick_size: f64,
    value: f64,
    count: usize,
    initialized: bool,
    has_inputs: bool,
}

impl Display for MicroSkewFactor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for MicroSkewFactor {
    fn name(&self) -> String {
        stringify!(MicroSkewFactor).to_string()
    }

    fn has_inputs(&self) -> bool {
        self.has_inputs
    }

    fn initialized(&self) -> bool {
        self.initialized
    }

    fn handle_book(&mut self, book: &OrderBook) {
        let bid = book.best_bid_price().map(|p| p.as_f64());
        let ask = book.best_ask_price().map(|p| p.as_f64());
        let bid_qty = book.best_bid_size().map(|q| q.as_f64());
        let ask_qty = book.best_ask_size().map(|q| q.as_f64());
        self.update(bid, bid_qty, ask, ask_qty);
    }

    fn reset(&mut self) {
        *self = Self::default();
    }
}

impl MicroSkewFactor {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            tick_size: 0.0,
            value: 0.0,
            count: 0,
            initialized: false,
            has_inputs: false,
        }
    }

    pub fn set_tick_size(&mut self, tick_size: f64) {
        self.tick_size = tick_size.max(1e-9);
    }

    #[allow(clippy::too_many_arguments)]
    pub fn update(
        &mut self,
        bid_price: Option<f64>,
        bid_qty: Option<f64>,
        ask_price: Option<f64>,
        ask_qty: Option<f64>,
    ) {
        self.has_inputs = true;
        self.count += 1;

        match (bid_price, bid_qty, ask_price, ask_qty) {
            (Some(bp), Some(bq), Some(ap), Some(aq)) => {
                let mid = (ap + bp) * 0.5;
                if mid <= 0.0 {
                    self.value = 0.0;
                    self.initialized = false;
                    return;
                }
                let total_qty = bq + aq;
                let micro = if total_qty > f64::EPSILON {
                    (ap * bq + bp * aq) / total_qty
                } else {
                    mid
                };
                let tick = self.tick_size.max(1e-9);
                self.value = (micro - mid) / tick;
                self.initialized = true;
            }
            _ => {
                self.value = 0.0;
                self.initialized = false;
            }
        }
    }
}

impl ValueIndicator for MicroSkewFactor {
    fn value(&self) -> f64 {
        self.value
    }
}
