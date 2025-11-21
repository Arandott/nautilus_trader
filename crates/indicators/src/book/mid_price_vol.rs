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

use std::fmt::Display;

use nautilus_model::orderbook::OrderBook;

use crate::indicator::Indicator;

const MIN_DECAY: f64 = 1e-6;
const MAX_DECAY: f64 = 0.999_999;

fn clamp_decay(decay: f64) -> f64 {
    if decay.is_nan() {
        0.94
    } else {
        decay.clamp(MIN_DECAY, MAX_DECAY)
    }
}

#[repr(C)]
#[derive(Debug)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(module = "nautilus_trader.core.nautilus_pyo3.indicators")
)]
pub struct BookMidPriceVolEstimator {
    decay: f64,
    last_mid: Option<f64>,
    variance: f64,
    count: usize,
    initialized: bool,
    has_inputs: bool,
}

impl Display for BookMidPriceVolEstimator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for BookMidPriceVolEstimator {
    fn name(&self) -> String {
        stringify!(BookMidPriceVolEstimator).to_string()
    }

    fn has_inputs(&self) -> bool {
        self.has_inputs
    }

    fn initialized(&self) -> bool {
        self.initialized
    }

    fn handle_book(&mut self, book: &OrderBook) {
        if let (Some(bid), Some(ask)) = (book.best_bid_price(), book.best_ask_price()) {
            let mid = (bid.as_f64() + ask.as_f64()) * 0.5;
            self.update(mid);
        }
    }

    fn reset(&mut self) {
        self.last_mid = None;
        self.variance = 0.0;
        self.count = 0;
        self.has_inputs = false;
        self.initialized = false;
    }
}

impl BookMidPriceVolEstimator {
    /// Creates a new estimator with the provided decay factor (default 0.94).
    #[must_use]
    pub fn new(decay: f64) -> Self {
        Self {
            decay: clamp_decay(decay),
            last_mid: None,
            variance: 0.0,
            count: 0,
            initialized: false,
            has_inputs: false,
        }
    }

    fn weight(&self) -> f64 {
        1.0 - self.decay
    }

    #[allow(clippy::cast_precision_loss)]
    fn normalize_mid(mid: f64) -> f64 {
        if mid.is_finite() {
            mid
        } else {
            0.0
        }
    }

    pub fn update(&mut self, mid: f64) {
        let mid = Self::normalize_mid(mid);
        self.has_inputs = true;
        if let Some(last) = self.last_mid {
            let denom = last.abs().max(1e-12);
            let ret = (mid - last) / denom;
            self.variance = self.decay * self.variance + self.weight() * ret * ret;
            self.count += 1;
            self.initialized = true;
        }
        self.last_mid = Some(mid);
    }

    #[must_use]
    pub fn sigma_rel(&self) -> f64 {
        self.variance.sqrt()
    }

    #[must_use]
    pub fn sigma_px(&self, mid: f64) -> f64 {
        self.sigma_rel() * mid
    }

    #[must_use]
    pub const fn count(&self) -> usize {
        self.count
    }

    #[must_use]
    pub fn decay(&self) -> f64 {
        self.decay
    }
}

////////////////////////////////////////////////////////////////////////////////
// Tests
////////////////////////////////////////////////////////////////////////////////
#[cfg(test)]
mod tests {
    use nautilus_model::stubs::stub_order_book_mbp_appl_xnas;
    use rstest::rstest;

    use super::*;

    #[rstest]
    fn test_default_state() {
        let est = BookMidPriceVolEstimator::new(0.94);
        assert_eq!(format!("{est}"), "BookMidPriceVolEstimator()");
        assert_eq!(est.decay(), 0.94);
        assert_eq!(est.count, 0);
        assert_eq!(est.sigma_rel(), 0.0);
        assert!(!est.initialized());
        assert!(!est.has_inputs());
    }

    #[rstest]
    fn test_update_sequence() {
        let mut est = BookMidPriceVolEstimator::new(0.5);
        est.update(100.0);
        assert_eq!(est.count, 0);
        assert!(!est.initialized());

        est.update(101.0);
        assert_eq!(est.count, 1);
        assert!(est.initialized());
        assert!(est.sigma_rel() > 0.0);
    }

    #[rstest]
    fn test_handle_book() {
        let mut est = BookMidPriceVolEstimator::new(0.9);
        let book = stub_order_book_mbp_appl_xnas();
        est.handle_book(&book);
        est.handle_book(&book);
        assert!(est.initialized());
        assert!(est.sigma_rel() >= 0.0);
    }

    #[rstest]
    fn test_reset() {
        let mut est = BookMidPriceVolEstimator::new(0.9);
        est.update(100.0);
        est.update(101.0);
        est.reset();
        assert_eq!(est.count, 0);
        assert_eq!(est.sigma_rel(), 0.0);
        assert!(!est.initialized());
    }
}
