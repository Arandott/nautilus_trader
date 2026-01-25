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

use super::super::BOOK_LEVELS;
use crate::aurora_indicators::utils::{LagBuffer, RollingCorrelation, RollingWindow};

#[derive(Debug)]
#[allow(dead_code)]
pub(super) struct BookFactorState {
    pub(super) value: f64,
    pub(super) count: usize,
    pub(super) initialized: bool,
    pub(super) has_inputs: bool,
    pub(super) rolling_a: RollingWindow,
    pub(super) rolling_b: RollingWindow,
    pub(super) rolling_c: RollingWindow,
    pub(super) corr_a: RollingCorrelation,
    pub(super) corr_b: RollingCorrelation,
    pub(super) lag_a: LagBuffer,
    pub(super) lag_b: LagBuffer,
    pub(super) last_trade_price: Option<f64>,
    pub(super) last_trade_volume: Option<f64>,
    pub(super) last_price: Option<f64>,
    pub(super) last_mid: Option<f64>,
    pub(super) last_mid_delta: Option<f64>,
    pub(super) last_volume: Option<f64>,
    pub(super) last_ret: Option<f64>,
    pub(super) last_spread: Option<f64>,
    pub(super) last_bid0: Option<f64>,
    pub(super) last_ask0: Option<f64>,
    pub(super) last_bid_amt0: Option<f64>,
    pub(super) direction_sign: f64,
    pub(super) direction_len: usize,
    pub(super) prev_bid_amts: [f64; BOOK_LEVELS],
    pub(super) prev_ask_amts: [f64; BOOK_LEVELS],
}

impl BookFactorState {
    #[must_use]
    pub(super) fn new(window: usize, window_secondary: usize) -> Self {
        let window = window.max(1);
        let window_secondary = window_secondary.max(1);
        Self {
            value: 0.0,
            count: 0,
            initialized: false,
            has_inputs: false,
            rolling_a: RollingWindow::new(window),
            rolling_b: RollingWindow::new(window_secondary),
            rolling_c: RollingWindow::new(window),
            corr_a: RollingCorrelation::new(window),
            corr_b: RollingCorrelation::new(window),
            lag_a: LagBuffer::new(1),
            lag_b: LagBuffer::new(5),
            last_trade_price: None,
            last_trade_volume: None,
            last_price: None,
            last_mid: None,
            last_mid_delta: None,
            last_volume: None,
            last_ret: None,
            last_spread: None,
            last_bid0: None,
            last_ask0: None,
            last_bid_amt0: None,
            direction_sign: 0.0,
            direction_len: 0,
            prev_bid_amts: [0.0; BOOK_LEVELS],
            prev_ask_amts: [0.0; BOOK_LEVELS],
        }
    }
}
