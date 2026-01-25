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

const NAME: &str = "ask_ladder_density";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;

/// Formula/logic: value = safe_div(avg_diff, avg_amt, DEFAULT_EPS)
/// Inputs: ask_amt, ask_price
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct AskLadderDensity {
    state: BookFactorState,
}

impl AskLadderDensity {
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

        let mut a0 = 0.0;
        let mut a1 = 0.0;
        let mut a2 = 0.0;
        let mut a3 = 0.0;
        let mut a4 = 0.0;
        let mut q0 = 0.0;
        let mut q1 = 0.0;
        let mut q2 = 0.0;
        let mut q3 = 0.0;
        let mut q4 = 0.0;
        for (idx, level) in book.asks(Some(5)).enumerate() {
            let price = level.price.value.as_f64();
            let size = level.size();
            match idx {
                0 => {
                    a0 = price;
                    q0 = size;
                }
                1 => {
                    a1 = price;
                    q1 = size;
                }
                2 => {
                    a2 = price;
                    q2 = size;
                }
                3 => {
                    a3 = price;
                    q3 = size;
                }
                4 => {
                    a4 = price;
                    q4 = size;
                }
                _ => {}
            }
        }
        let sum_diff = (a1 - a0) + (a2 - a1) + (a3 - a2) + (a4 - a3);
        let avg_diff = safe_div(sum_diff, 4.0, DEFAULT_EPS);
        let avg_amt = safe_div(q0 + q1 + q2 + q3 + q4, 5.0, DEFAULT_EPS);
        self.state.value = safe_div(avg_diff, avg_amt, DEFAULT_EPS);
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

impl Display for AskLadderDensity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for AskLadderDensity {
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

impl ValueIndicator for AskLadderDensity {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::AskLadderDensity;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_ask_ladder_density_value() {
        let book = sample_book();
        let mut factor = AskLadderDensity::new();
        factor.handle_book(&book);
        let mut bid_prices = [0.0; BOOK_LEVELS];
        let mut ask_prices = [0.0; BOOK_LEVELS];
        let mut bid_amts = [0.0; BOOK_LEVELS];
        let mut ask_amts = [0.0; BOOK_LEVELS];
        fill_book_levels(&book, &mut bid_prices, &mut bid_amts, &mut ask_prices, &mut ask_amts);
        let diffs = [
            ask_prices[1] - ask_prices[0],
            ask_prices[2] - ask_prices[1],
            ask_prices[3] - ask_prices[2],
            ask_prices[4] - ask_prices[3],
        ];
        let avg_diff = mean(&diffs);
        let avg_amt = mean(&ask_amts[..5]);
        let expected = safe_div(avg_diff, avg_amt, DEFAULT_EPS);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_ask_ladder_density_empty_book() {
        let book = empty_book();
        let mut factor = AskLadderDensity::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert!(factor.value().is_finite());
    }
}
