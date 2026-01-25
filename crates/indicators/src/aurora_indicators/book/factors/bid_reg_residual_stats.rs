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

const NAME: &str = "bid_reg_residual_stats";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;
/// Formula/logic: rolling push: std(&residuals); value = rolling_a.mean()
/// Inputs: bid_price
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct BidRegResidualStats {
    state: BookFactorState,
}

impl BidRegResidualStats {
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

        let n = 5.0;
        let sum_x = 10.0;
        let sum_x2 = 30.0;
        let mut sum_y = 0.0;
        let mut sum_xy = 0.0;
        for (idx, level) in book.bids(Some(5)).enumerate() {
            let y = level.price.value.as_f64();
            let x = idx as f64;
            sum_y += y;
            sum_xy += x * y;
        }
        let denom = n * sum_x2 - sum_x * sum_x;
        let slope = safe_div(n * sum_xy - sum_x * sum_y, denom, DEFAULT_EPS);
        let mean_x = sum_x / n;
        let mean_y = sum_y / n;
        let intercept = mean_y - slope * mean_x;
        let mut count = 0.0;
        let mut mean = 0.0;
        let mut m2 = 0.0;
        let mut idx = 0usize;
        for level in book.bids(Some(5)) {
            let y = level.price.value.as_f64();
            let x = idx as f64;
            let res = y - (intercept + slope * x);
            count += 1.0;
            let delta = res - mean;
            mean += delta / count;
            let delta2 = res - mean;
            m2 += delta * delta2;
            idx += 1;
        }
        for i in idx..5 {
            let x = i as f64;
            let res = 0.0 - (intercept + slope * x);
            count += 1.0;
            let delta = res - mean;
            mean += delta / count;
            let delta2 = res - mean;
            m2 += delta * delta2;
        }
        let var = if count <= 0.0 {
            0.0
        } else {
            safe_div(m2, count, DEFAULT_EPS)
        };
        let res_std = safe_sqrt(var);
        self.state.rolling_a.push(res_std);
        self.state.value = self.state.rolling_a.mean();
        self.state.initialized = self.state.rolling_a.is_full();

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

impl Display for BidRegResidualStats {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for BidRegResidualStats {
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

impl ValueIndicator for BidRegResidualStats {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::BidRegResidualStats;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_bid_reg_residual_stats_value() {
        let book = sample_book();
        let mut factor = BidRegResidualStats::new();
        factor.handle_book(&book);
        let mut bid_prices = [0.0; BOOK_LEVELS];
        let mut ask_prices = [0.0; BOOK_LEVELS];
        let mut bid_amts = [0.0; BOOK_LEVELS];
        let mut ask_amts = [0.0; BOOK_LEVELS];
        fill_book_levels(&book, &mut bid_prices, &mut bid_amts, &mut ask_prices, &mut ask_amts);
        let x = index_array::<5>();
        let slope = ols_slope(&x, &bid_prices[..5]);
        let intercept = mean(&bid_prices[..5]) - slope * mean(&x);
        let mut residuals = [0.0; 5];
        for i in 0..5 {
            residuals[i] = bid_prices[i] - (intercept + slope * x[i]);
        }
        let expected = std(&residuals);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_bid_reg_residual_stats_empty_book() {
        let book = empty_book();
        let mut factor = BidRegResidualStats::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert!(factor.value().is_finite());
    }
}
