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

const NAME: &str = "ofi_cum_L";
const WINDOW: usize = 60;
const WINDOW_SECONDARY: usize = 60;

/// Formula/logic: value = ofi
/// Inputs: ask_amt, bid_amt
/// Output: state.value (factor value)
#[derive(Debug)]
pub struct OfiCumL {
    state: BookFactorState,
}

impl OfiCumL {
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
        let mut ofi = 0.0;
        let mut bid_iter = book.bids(Some(depth));
        let mut ask_iter = book.asks(Some(depth));
        for i in 0..depth {
            let bid_amt = bid_iter.next().map(|level| level.size()).unwrap_or(0.0);
            let ask_amt = ask_iter.next().map(|level| level.size()).unwrap_or(0.0);
            let delta_bid = bid_amt - self.state.prev_bid_amts[i];
            let delta_ask = ask_amt - self.state.prev_ask_amts[i];
            ofi += delta_bid - delta_ask;
            self.state.prev_bid_amts[i] = bid_amt;
            self.state.prev_ask_amts[i] = ask_amt;
        }
        self.state.value = ofi;
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

impl Display for OfiCumL {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", NAME)
    }
}

impl Indicator for OfiCumL {
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

impl ValueIndicator for OfiCumL {
    fn value(&self) -> f64 {
        self.state.value
    }
}

#[cfg(test)]
mod tests {
    use super::super::prelude::*;
    use super::super::test_utils::{empty_book, sample_book};
    use super::OfiCumL;
    use crate::aurora_indicators::ValueIndicator;
    use crate::indicator::Indicator;
    use approx::assert_relative_eq;

    #[test]
    fn test_ofi_cum_l_value() {
        let book = sample_book();
        let mut factor = OfiCumL::new();
        for i in 0..5 {
            factor.state.prev_bid_amts[i] = 50.0 + i as f64;
            factor.state.prev_ask_amts[i] = 10.0 + i as f64;
        }
        factor.handle_book(&book);

        let depth = 5;
        let mut bid_iter = book.bids(Some(depth));
        let mut ask_iter = book.asks(Some(depth));
        let mut expected = 0.0;
        for i in 0..depth {
            let bid_amt = bid_iter.next().map(|level| level.size()).unwrap_or(0.0);
            let ask_amt = ask_iter.next().map(|level| level.size()).unwrap_or(0.0);
            let prev_bid = 50.0 + i as f64;
            let prev_ask = 10.0 + i as f64;
            expected += (bid_amt - prev_bid) - (ask_amt - prev_ask);
        }
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), expected);
    }

    #[test]
    fn test_ofi_cum_l_empty_book() {
        let book = empty_book();
        let mut factor = OfiCumL::new();
        factor.handle_book(&book);
        assert!(factor.has_inputs());
        assert_relative_eq!(factor.value(), 0.0);
    }
}
