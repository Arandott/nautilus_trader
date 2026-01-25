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

const NAME: &str = "lvl5_avg_price_ratio_sum";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;

/// Formula/logic: value = safe_div(bid_avg, input.bid_prices[0], DEFAULT_EPS) + safe_div(ask_avg, input.ask_prices[0], DEFAULT_EPS)
/// Inputs: ask_price, bid_price
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct Lvl5AvgPriceRatioSum {
    state: BookFactorState,
}

impl Lvl5AvgPriceRatioSum {
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

        let depth = 5;
        let bid_sum: f64 = book
            .bids(Some(depth))
            .map(|level| level.price.value.as_f64())
            .sum();
        let ask_sum: f64 = book
            .asks(Some(depth))
            .map(|level| level.price.value.as_f64())
            .sum();
        let bid_avg = safe_div(bid_sum, depth as f64, DEFAULT_EPS);
        let ask_avg = safe_div(ask_sum, depth as f64, DEFAULT_EPS);
        let bid0 = book.best_bid_price().map(|price| price.as_f64()).unwrap_or(0.0);
        let ask0 = book.best_ask_price().map(|price| price.as_f64()).unwrap_or(0.0);
        self.state.value =
            safe_div(bid_avg, bid0, DEFAULT_EPS) + safe_div(ask_avg, ask0, DEFAULT_EPS);
        self.state.initialized = true;

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

impl Display for Lvl5AvgPriceRatioSum {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for Lvl5AvgPriceRatioSum {
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

impl ValueIndicator for Lvl5AvgPriceRatioSum {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::Lvl5AvgPriceRatioSum;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_lvl5_avg_price_ratio_sum_value() {
        let book = sample_book();
        let mut factor = Lvl5AvgPriceRatioSum::new();
        factor.handle_book(&book);

        let depth = 5;
        let bid_sum: f64 = book
            .bids(Some(depth))
            .map(|level| level.price.value.as_f64())
            .sum();
        let ask_sum: f64 = book
            .asks(Some(depth))
            .map(|level| level.price.value.as_f64())
            .sum();
        let bid_avg = safe_div(bid_sum, depth as f64, DEFAULT_EPS);
        let ask_avg = safe_div(ask_sum, depth as f64, DEFAULT_EPS);
        let bid0 = book.best_bid_price().map(|price| price.as_f64()).unwrap_or(0.0);
        let ask0 = book.best_ask_price().map(|price| price.as_f64()).unwrap_or(0.0);
        let expected =
            safe_div(bid_avg, bid0, DEFAULT_EPS) + safe_div(ask_avg, ask0, DEFAULT_EPS);

        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_lvl5_avg_price_ratio_sum_empty_book() {
        let book = empty_book();
        let mut factor = Lvl5AvgPriceRatioSum::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 0.0);
    }
}
