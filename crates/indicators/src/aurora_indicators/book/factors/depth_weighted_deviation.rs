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

use super::prelude::*;

const NAME: &str = "depth_weighted_deviation";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;

/// Formula/logic: value = safe_div(num, den, DEFAULT_EPS)
/// Inputs: bid_amt, bid_price, price
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct DepthWeightedDeviation {
    state: BookFactorState,
}

impl DepthWeightedDeviation {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: BookFactorState::new(WINDOW, WINDOW_SECONDARY),
        }
    }

    pub fn update(&mut self, book: &OrderBook) {
        let last_price = self.state.last_trade_price;
        let volume = self.state.last_trade_volume;
        let ret = self.state.last_ret;
        let (mid_price, spread) = mid_and_spread(book);

        self.state.count += 1;
        self.state.has_inputs = true;

        if let Some(price) = last_price {
            let mut num = 0.0;
            let mut den = 0.0;
            for (idx, level) in book.bids(Some(5)).enumerate() {
                if idx < 5 {
                    let bid_price = level.price.value.as_f64();
                    let qty = level.size();
                    num += qty * (price - bid_price);
                    den += qty;
                }
            }
            self.state.value = safe_div(num, den, DEFAULT_EPS);
            self.state.initialized = true;
        }

        if let Some(price) = last_price {
            self.state.last_price = Some(price);
        }
        if let Some(vol) = volume {
            self.state.last_volume = Some(vol);
        }
        if let Some(r) = ret {
            self.state.last_ret = Some(r);
        }
        if let Some(mid) = mid_price {
            self.state.last_mid = Some(mid);
        }
        if let Some(spread) = spread {
            self.state.last_spread = Some(spread);
        }
    }
}

impl Display for DepthWeightedDeviation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for DepthWeightedDeviation {
    fn name(&self) -> String {
        NAME.to_string()
    }

    fn has_inputs(&self) -> bool {
        self.state.has_inputs
    }

    fn initialized(&self) -> bool {
        self.state.initialized
    }

    fn handle_book(&mut self, book: &OrderBook) {
        self.update(book);
    }

    fn handle_trade(&mut self, trade: &TradeTick) {
        let price = trade.price.as_f64();
        let volume = trade.size.as_f64();
        let ret = self
            .state
            .last_trade_price
            .map(|prev| safe_div(price - prev, prev, DEFAULT_EPS));
        self.state.last_trade_price = Some(price);
        self.state.last_trade_volume = Some(volume);
        self.state.last_ret = ret;
    }

    fn reset(&mut self) {
        *self = Self::new();
    }
}

impl ValueIndicator for DepthWeightedDeviation {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::DepthWeightedDeviation;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;
    use nautilus_model::data::stubs::stub_trade_ethusdt_buyer;
    use nautilus_model::types::{Price, Quantity};

    #[test]
    fn test_depth_weighted_deviation_value() {
        let book = sample_book();
        let mut factor = DepthWeightedDeviation::new();
        let mut trade = stub_trade_ethusdt_buyer();
        trade.price = Price::from("100.5");
        trade.size = Quantity::from("10");
        factor.handle_trade(&trade);
        factor.handle_book(&book);
        let price = trade.price.as_f64();
        let mut num = 0.0;
        let mut den = 0.0;
        for (idx, level) in book.bids(Some(5)).enumerate() {
            if idx < 5 {
                let bid_price = level.price.value.as_f64();
                let qty = level.size();
                num += qty * (price - bid_price);
                den += qty;
            }
        }
        let expected = safe_div(num, den, DEFAULT_EPS);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_depth_weighted_deviation_empty_book() {
        let book = empty_book();
        let mut factor = DepthWeightedDeviation::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 0.0);
    }
}
