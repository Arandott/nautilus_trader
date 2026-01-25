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
use crate::book::mid_price_vol::BookMidPriceVolEstimator;
use crate::indicator::Indicator;

#[repr(C)]
#[derive(Debug)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(module = "nautilus_trader.core.nautilus_pyo3.indicators")
)]
pub struct SigmaRelFactor {
    base_sigma: f64,
    estimator: BookMidPriceVolEstimator,
}

impl Default for SigmaRelFactor {
    fn default() -> Self {
        Self::new(0.94)
    }
}

impl Display for SigmaRelFactor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for SigmaRelFactor {
    fn name(&self) -> String {
        stringify!(SigmaRelFactor).to_string()
    }

    fn has_inputs(&self) -> bool {
        self.estimator.has_inputs()
    }

    fn initialized(&self) -> bool {
        self.estimator.initialized()
    }

    fn handle_book(&mut self, book: &OrderBook) {
        self.estimator.handle_book(book);
    }

    fn reset(&mut self) {
        self.estimator.reset();
    }
}

impl SigmaRelFactor {
    #[must_use]
    pub fn new(decay: f64) -> Self {
        Self {
            base_sigma: 0.0,
            estimator: BookMidPriceVolEstimator::new(decay),
        }
    }

    pub fn set_base_sigma(&mut self, base_sigma: f64) {
        self.base_sigma = base_sigma.max(0.0);
    }
}

impl ValueIndicator for SigmaRelFactor {
    fn value(&self) -> f64 {
        if self.estimator.count() > 0 {
            self.estimator.sigma_rel()
        } else {
            self.base_sigma
        }
    }
}
