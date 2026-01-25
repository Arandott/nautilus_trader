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

use nautilus_model::orderbook::OrderBook;

use super::BOOK_LEVELS;

#[derive(Clone, Debug)]
pub struct BookInput {
    pub bid_prices: [f64; BOOK_LEVELS],
    pub ask_prices: [f64; BOOK_LEVELS],
    pub bid_amts: [f64; BOOK_LEVELS],
    pub ask_amts: [f64; BOOK_LEVELS],
    pub mid_price: Option<f64>,
    pub spread: Option<f64>,
    pub last_price: Option<f64>,
    pub volume: Option<f64>,
    pub ret: Option<f64>,
    pub vwap: Option<f64>,
    pub twap: Option<f64>,
    pub tvr: Option<f64>,
    pub order_age: Option<f64>,
    pub midp11riserate: Option<f64>,
    pub midp11riserate_100: Option<f64>,
    pub cumbid: Option<f64>,
    pub cumask: Option<f64>,
    pub cumvol: Option<f64>,
    pub abv5mean: Option<f64>,
}

impl Default for BookInput {
    fn default() -> Self {
        Self {
            bid_prices: [0.0; BOOK_LEVELS],
            ask_prices: [0.0; BOOK_LEVELS],
            bid_amts: [0.0; BOOK_LEVELS],
            ask_amts: [0.0; BOOK_LEVELS],
            mid_price: None,
            spread: None,
            last_price: None,
            volume: None,
            ret: None,
            vwap: None,
            twap: None,
            tvr: None,
            order_age: None,
            midp11riserate: None,
            midp11riserate_100: None,
            cumbid: None,
            cumask: None,
            cumvol: None,
            abv5mean: None,
        }
    }
}

impl BookInput {
    #[must_use]
    pub fn from_book(book: &OrderBook) -> Self {
        let mut input = Self::default();
        for (idx, level) in book.bids(Some(BOOK_LEVELS)).enumerate() {
            if idx >= BOOK_LEVELS {
                break;
            }
            input.bid_prices[idx] = level.price.value.as_f64();
            input.bid_amts[idx] = level.size();
        }
        for (idx, level) in book.asks(Some(BOOK_LEVELS)).enumerate() {
            if idx >= BOOK_LEVELS {
                break;
            }
            input.ask_prices[idx] = level.price.value.as_f64();
            input.ask_amts[idx] = level.size();
        }
        if let (Some(bid), Some(ask)) = (book.best_bid_price(), book.best_ask_price()) {
            let bid = bid.as_f64();
            let ask = ask.as_f64();
            input.mid_price = Some((bid + ask) * 0.5);
            input.spread = Some(ask - bid);
        }
        input
    }

    #[inline]
    #[must_use]
    pub fn bid_sum(&self, depth: usize) -> f64 {
        self.bid_amts.iter().take(depth.min(BOOK_LEVELS)).sum()
    }

    #[inline]
    #[must_use]
    pub fn ask_sum(&self, depth: usize) -> f64 {
        self.ask_amts.iter().take(depth.min(BOOK_LEVELS)).sum()
    }

    #[inline]
    #[must_use]
    pub fn bid_notional_sum(&self, depth: usize) -> f64 {
        self.bid_prices
            .iter()
            .zip(self.bid_amts.iter())
            .take(depth.min(BOOK_LEVELS))
            .map(|(p, q)| p * q)
            .sum()
    }

    #[inline]
    #[must_use]
    pub fn ask_notional_sum(&self, depth: usize) -> f64 {
        self.ask_prices
            .iter()
            .zip(self.ask_amts.iter())
            .take(depth.min(BOOK_LEVELS))
            .map(|(p, q)| p * q)
            .sum()
    }

    #[inline]
    #[must_use]
    pub fn bid_price_avg(&self, start: usize, end: usize) -> f64 {
        let end = end.min(BOOK_LEVELS);
        if start >= end {
            return 0.0;
        }
        let slice = &self.bid_prices[start..end];
        let sum: f64 = slice.iter().sum();
        sum / slice.len() as f64
    }

    #[inline]
    #[must_use]
    pub fn ask_price_avg(&self, start: usize, end: usize) -> f64 {
        let end = end.min(BOOK_LEVELS);
        if start >= end {
            return 0.0;
        }
        let slice = &self.ask_prices[start..end];
        let sum: f64 = slice.iter().sum();
        sum / slice.len() as f64
    }
}
