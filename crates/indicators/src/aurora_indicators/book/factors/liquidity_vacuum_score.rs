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

const NAME: &str = "liquidity_vacuum_score";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;

/// Formula/logic: value = if spread_up && ask_down && ret > 0.0 { 1.0 } else { 0.0 }
/// Inputs: ask_amt, ret, spread
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct LiquidityVacuumScore {
    state: BookFactorState,
}

impl LiquidityVacuumScore {
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
        let ask0 = book.best_ask_size().map(|size| size.as_f64()).unwrap_or(0.0);

        self.state.count += 1;
        self.state.has_inputs = true;

        if let (Some(spread), Some(ret)) = (spread, ret) {
            let spread_up = self.state.last_spread.map(|prev| spread > prev).unwrap_or(false);
            let ask_down = self.state.last_ask0.map(|prev| ask0 < prev).unwrap_or(false);
            self.state.value = if spread_up && ask_down && ret > 0.0 { 1.0 } else { 0.0 };
            self.state.initialized = true;
            self.state.last_spread = Some(spread);
            self.state.last_ask0 = Some(ask0);
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

impl Display for LiquidityVacuumScore {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for LiquidityVacuumScore {
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

impl ValueIndicator for LiquidityVacuumScore {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::LiquidityVacuumScore;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_liquidity_vacuum_score_value() {
        let book = sample_book();
        let mut factor = LiquidityVacuumScore::new();
        factor.state.last_spread = Some(0.5);
        factor.state.last_ask0 = Some(200.0);
        factor.state.last_ret = Some(0.01);
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 1.0);
    }

    #[test]
    fn test_liquidity_vacuum_score_empty_book() {
        let book = empty_book();
        let mut factor = LiquidityVacuumScore::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 0.0);
    }
}
