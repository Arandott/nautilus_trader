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

#[repr(C)]
#[derive(Debug)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(module = "nautilus_trader.core.nautilus_pyo3.indicators")
)]
pub struct BookL1Factors {
    pub bid_price: Option<f64>,
    pub ask_price: Option<f64>,
    pub bid_qty: Option<f64>,
    pub ask_qty: Option<f64>,
    pub mid: Option<f64>,
    pub microprice: Option<f64>,
    pub imbalance: Option<f64>,
    pub spread: Option<f64>,
    pub has_market: bool,
    pub count: usize,
    pub initialized: bool,
    has_inputs: bool,
}

impl Default for BookL1Factors {
    fn default() -> Self {
        Self::new()
    }
}

impl Display for BookL1Factors {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for BookL1Factors {
    fn name(&self) -> String {
        stringify!(BookL1Factors).to_string()
    }

    fn has_inputs(&self) -> bool {
        self.has_inputs
    }

    fn initialized(&self) -> bool {
        self.initialized
    }

    fn handle_book(&mut self, book: &OrderBook) {
        let bid_price = book.best_bid_price().map(|p| p.as_f64());
        let ask_price = book.best_ask_price().map(|p| p.as_f64());
        let bid_qty = book.best_bid_size().map(|q| q.as_f64());
        let ask_qty = book.best_ask_size().map(|q| q.as_f64());
        self.update(bid_price, bid_qty, ask_price, ask_qty);
    }

    fn reset(&mut self) {
        *self = Self::new();
    }
}

impl BookL1Factors {
    /// Creates a new [`BookL1Factors`] instance.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            bid_price: None,
            ask_price: None,
            bid_qty: None,
            ask_qty: None,
            mid: None,
            microprice: None,
            imbalance: None,
            spread: None,
            has_market: false,
            count: 0,
            initialized: false,
            has_inputs: false,
        }
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

        self.bid_price = bid_price;
        self.ask_price = ask_price;
        self.bid_qty = bid_qty;
        self.ask_qty = ask_qty;

        match (bid_price, bid_qty, ask_price, ask_qty) {
            (Some(bp), Some(bq), Some(ap), Some(aq)) => {
                let spread = ap - bp;
                let mid = (ap + bp) * 0.5;
                let total_qty = bq + aq;

                self.spread = Some(spread);
                self.mid = Some(mid);

                if total_qty > f64::EPSILON {
                    let micro = (ap * bq + bp * aq) / total_qty;
                    let imbalance = (bq - aq) / total_qty;
                    self.microprice = Some(micro);
                    self.imbalance = Some(imbalance);
                } else {
                    self.microprice = Some(mid);
                    self.imbalance = Some(0.0);
                }

                self.has_market = true;
                self.initialized = true;
            }
            _ => {
                self.spread = None;
                self.mid = None;
                self.microprice = None;
                self.imbalance = None;
                self.has_market = false;
            }
        }
    }
}

////////////////////////////////////////////////////////////////////////////////
// Tests
////////////////////////////////////////////////////////////////////////////////
#[cfg(test)]
mod tests {
    use approx::assert_relative_eq;
    use nautilus_model::{
        identifiers::InstrumentId,
        stubs::{stub_order_book_mbp, stub_order_book_mbp_appl_xnas},
    };
    use rstest::rstest;

    use super::*;

    #[rstest]
    fn test_default_state() {
        let factors = BookL1Factors::new();
        assert_eq!(factors.count, 0);
        assert!(!factors.has_market);
        assert!(!factors.initialized);
        assert!(!factors.has_inputs());
        assert_eq!(format!("{factors}"), "BookL1Factors()");
    }

    #[rstest]
    fn test_handle_balanced_book() {
        let mut factors = BookL1Factors::new();
        let book = stub_order_book_mbp_appl_xnas();
        factors.handle_book(&book);

        assert_eq!(factors.count, 1);
        assert!(factors.has_market);
        assert_relative_eq!(factors.spread.unwrap(), 1.0);
        assert_relative_eq!(factors.mid.unwrap(), 100.5);
        assert_relative_eq!(factors.microprice.unwrap(), 100.5);
        assert_relative_eq!(factors.imbalance.unwrap(), 0.0);
    }

    #[rstest]
    fn test_handle_imbalanced_book() {
        let mut factors = BookL1Factors::new();
        let book = stub_order_book_mbp(
            InstrumentId::from("AAPL.XNAS"),
            101.0,
            100.0,
            100.0,
            200.0,
            2,
            0.01,
            0,
            100.0,
            10,
        );
        factors.handle_book(&book);

        assert_eq!(factors.count, 1);
        assert!(factors.has_market);
        assert_relative_eq!(factors.spread.unwrap(), 1.0);
        assert_relative_eq!(factors.mid.unwrap(), 100.5);
        assert_relative_eq!(
            factors.microprice.unwrap(),
            (101.0 * 200.0 + 100.0 * 100.0) / 300.0
        );
        assert_relative_eq!(factors.imbalance.unwrap(), (200.0 - 100.0) / 300.0);
    }

    #[rstest]
    fn test_update_missing_side() {
        let mut factors = BookL1Factors::new();
        factors.update(Some(100.0), Some(50.0), None, None);

        assert_eq!(factors.count, 1);
        assert!(!factors.has_market);
        assert!(factors.mid.is_none());
        assert!(factors.microprice.is_none());
        assert!(factors.imbalance.is_none());
    }
}
