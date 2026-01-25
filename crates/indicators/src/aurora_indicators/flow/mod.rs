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

//! Aurora flow (bar/trade) factors.

use nautilus_model::data::Bar;

#[derive(Clone, Debug)]
pub struct FlowInput {
    pub open: Option<f64>,
    pub high: Option<f64>,
    pub low: Option<f64>,
    pub close: Option<f64>,
    pub volume: Option<f64>,
    pub ret: Option<f64>,
    pub logret: Option<f64>,
    pub mid_price: Option<f64>,
    pub vwap: Option<f64>,
    pub twap: Option<f64>,
    pub turnover: Option<f64>,
    pub bid_price: Option<f64>,
    pub ask_price: Option<f64>,
    pub cumbid: Option<f64>,
    pub cumask: Option<f64>,
    pub cumvol: Option<f64>,
    pub abv5mean: Option<f64>,
    pub midp11riserate: Option<f64>,
    pub midp11riserate_100: Option<f64>,
    pub sell_vwap: Option<f64>,
    pub bidvol: Option<f64>,
    pub askvol: Option<f64>,
}

impl Default for FlowInput {
    fn default() -> Self {
        Self {
            open: None,
            high: None,
            low: None,
            close: None,
            volume: None,
            ret: None,
            logret: None,
            mid_price: None,
            vwap: None,
            twap: None,
            turnover: None,
            bid_price: None,
            ask_price: None,
            cumbid: None,
            cumask: None,
            cumvol: None,
            abv5mean: None,
            midp11riserate: None,
            midp11riserate_100: None,
            sell_vwap: None,
            bidvol: None,
            askvol: None,
        }
    }
}

impl FlowInput {
    #[must_use]
    pub fn from_bar(bar: &Bar) -> Self {
        let open = bar.open.as_f64();
        let high = bar.high.as_f64();
        let low = bar.low.as_f64();
        let close = bar.close.as_f64();
        let volume = bar.volume.as_f64();
        let mid = (high + low) * 0.5;

        Self {
            open: Some(open),
            high: Some(high),
            low: Some(low),
            close: Some(close),
            volume: Some(volume),
            mid_price: Some(mid),
            ..Self::default()
        }
    }
}

pub mod factors;

pub use factors::*;
