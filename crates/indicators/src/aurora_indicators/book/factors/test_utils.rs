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

use super::super::BookInput;
use crate::aurora_indicators::book::BOOK_LEVELS;
use nautilus_model::{
    enums::BookType,
    identifiers::InstrumentId,
    orderbook::OrderBook,
    stubs::stub_order_book_mbp,
};

pub const TEST_ITERS: usize = 60;

pub fn sample_book() -> OrderBook {
    stub_order_book_mbp(
        InstrumentId::from("AAPL.XNAS"),
        101.0,
        100.0,
        100.0,
        100.0,
        2,
        0.01,
        0,
        100.0,
        BOOK_LEVELS,
    )
}

pub fn empty_book() -> OrderBook {
    OrderBook::new(InstrumentId::from("AAPL.XNAS"), BookType::L2_MBP)
}

pub fn sample_input() -> BookInput {
    let mut input = BookInput::default();
    for i in 0..BOOK_LEVELS {
        input.bid_prices[i] = 100.0 - i as f64;
        input.ask_prices[i] = 101.0 + i as f64;
        input.bid_amts[i] = 10.0 + i as f64;
        input.ask_amts[i] = 12.0 + i as f64;
    }
    input.mid_price = Some(100.5);
    input.spread = Some(1.0);
    input.last_price = Some(100.6);
    input.volume = Some(5.0);
    input.ret = Some(0.001);
    input.vwap = Some(100.55);
    input.twap = Some(100.5);
    input.tvr = Some(1000.0);
    input.order_age = Some(12.0);
    input.midp11riserate = Some(0.01);
    input.midp11riserate_100 = Some(0.02);
    input.cumbid = Some(50.0);
    input.cumask = Some(60.0);
    input.cumvol = Some(120.0);
    input.abv5mean = Some(15.0);
    input
}
