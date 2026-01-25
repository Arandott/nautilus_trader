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

const NAME: &str = "ret_var_1m";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;
const TRADE_ONLY: bool = true;

/// Formula/logic: rolling push: ret * ret; value = rolling_a.sum()
/// Inputs: ret
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct RetVar1m {
    state: BookFactorState,
}

impl RetVar1m {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: BookFactorState::new(WINDOW, WINDOW_SECONDARY),
        }
    }

    fn update_trade_only(&mut self) {
        let last_price = self.state.last_trade_price;
        let volume = self.state.last_trade_volume;
        let ret = self.state.last_ret;

        self.state.count += 1;
        self.state.has_inputs = true;

        if let Some(ret) = ret {
            self.state.rolling_a.push(ret * ret);
            self.state.value = self.state.rolling_a.sum();
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
    }
}

impl Display for RetVar1m {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for RetVar1m {
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
        let (mid_price, spread) = mid_and_spread(book);
        if let Some(mid) = mid_price {
            self.state.last_mid = Some(mid);
        }
        if let Some(spread) = spread {
            self.state.last_spread = Some(spread);
        }
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

        if TRADE_ONLY {
            self.update_trade_only();
        }
    }

    fn reset(&mut self) {
        *self = Self::new();
    }
}

impl ValueIndicator for RetVar1m {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::RetVar1m;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;
    use nautilus_model::data::stubs::stub_trade_ethusdt_buyer;
    use nautilus_model::types::{Price, Quantity};

    #[test]
    fn test_ret_var_1m_value() {
        let book = sample_book();
        let mut factor = RetVar1m::new();
        let base_price = book.best_bid_price().unwrap().as_f64();
        let mut trade1 = stub_trade_ethusdt_buyer();
        trade1.instrument_id = book.instrument_id;
        trade1.price = Price::new(base_price, 2);
        trade1.size = Quantity::new(2.0, 0);
        factor.handle_trade(&trade1);
        let mut trade2 = trade1;
        trade2.price = Price::new(base_price + 1.0, 2);
        factor.handle_trade(&trade2);
        let ret = safe_div((base_price + 1.0) - base_price, base_price, DEFAULT_EPS);
        let expected = ret * ret;
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_ret_var_1m_empty_book() {
        let book = empty_book();
        let mut factor = RetVar1m::new();
        factor.handle_book(&book);
        assert!(!factor.has_inputs());
        assert!(factor.value().is_finite());
    }
}
