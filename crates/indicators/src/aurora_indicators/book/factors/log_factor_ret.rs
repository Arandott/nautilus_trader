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

const NAME: &str = "log_factor_ret";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;
const TRADE_ONLY: bool = true;

/// Formula/logic: value = (1.0 + ret).ln()
/// Inputs: ret
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct LogFactorRet {
    state: BookFactorState,
}

impl LogFactorRet {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: BookFactorState::new(WINDOW, WINDOW_SECONDARY),
        }
    }

    pub fn update(&mut self) {
        let last_price = self.state.last_trade_price;
        let volume = self.state.last_trade_volume;
        let ret = self.state.last_ret;

        self.state.count += 1;
        self.state.has_inputs = true;

        if let Some(ret) = ret {
            self.state.value = (1.0 + ret).ln();
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
    }
}

impl Display for LogFactorRet {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for LogFactorRet {
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
            self.update();
        }
    }

    fn reset(&mut self) {
        *self = Self::new();
    }
}

impl ValueIndicator for LogFactorRet {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::LogFactorRet;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;
    use nautilus_model::data::TradeTick;
    use nautilus_model::types::{Price, Quantity};

    #[test]
    fn test_log_factor_ret_trade_value() {
        let book = sample_book();
        let mut factor = LogFactorRet::new();
        let mut trade = TradeTick::default();
        trade.price = Price::from("100.0");
        trade.size = Quantity::from("1.0");
        factor.handle_trade(&trade);

        trade.price = Price::from("101.0");
        factor.handle_trade(&trade);

        factor.handle_book(&book);

        let expected = (1.0_f64 + 0.01).ln();
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_log_factor_ret_empty_book() {
        let book = empty_book();
        let mut factor = LogFactorRet::new();
        factor.handle_book(&book);
        assert_relative_eq!(factor.value(), 0.0);
    }
}
