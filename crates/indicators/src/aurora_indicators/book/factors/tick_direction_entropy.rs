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

const NAME: &str = "tick_direction_entropy";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;
/// Formula/logic: rolling push: sign(ret); value = entropy
/// Inputs: ret
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct TickDirectionEntropy {
    state: BookFactorState,
}

impl TickDirectionEntropy {
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
        let (mid_price, spread) = if let (Some(bid), Some(ask)) =
            (book.best_bid_price(), book.best_ask_price())
        {
            let bid = bid.as_f64();
            let ask = ask.as_f64();
            (Some((bid + ask) * 0.5), Some(ask - bid))
        } else {
            (None, None)
        };

        self.state.count += 1;
        self.state.has_inputs = true;

        if let Some(ret) = ret {
            let dir = sign(ret);
            self.state.rolling_a.push(dir);
            let up = self.state.rolling_a.values().iter().filter(|v| **v > 0.0).count();
            let down = self.state.rolling_a.values().iter().filter(|v| **v < 0.0).count();
            let total = self.state.rolling_a.len() as f64;
            let p_up = safe_div(up as f64, total, DEFAULT_EPS);
            let p_down = safe_div(down as f64, total, DEFAULT_EPS);
            let mut entropy = 0.0;
            if p_up > 0.0 {
                entropy -= p_up * p_up.ln();
            }
            if p_down > 0.0 {
                entropy -= p_down * p_down.ln();
            }
            self.state.value = entropy;
            self.state.initialized = self.state.rolling_a.is_full();
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

impl Display for TickDirectionEntropy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for TickDirectionEntropy {
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

impl ValueIndicator for TickDirectionEntropy {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::TickDirectionEntropy;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_tick_direction_entropy_value() {
        let book = sample_book();
        let mut factor = TickDirectionEntropy::new();
        factor.state.last_ret = Some(0.01);
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 0.0);
    }

    #[test]
    fn test_tick_direction_entropy_empty_book() {
        let book = empty_book();
        let mut factor = TickDirectionEntropy::new();
        factor.state.last_ret = Some(-0.02);
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert!(factor.value().is_finite());
    }
}
