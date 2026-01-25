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

use std::fmt::Display;

use nautilus_model::data::Bar;

use crate::{
    aurora_indicators::{
        utils::{
            diff_ratio, mean, safe_div, LagBuffer, RollingCorrelation, RollingLWMA, RollingWindow,
            DEFAULT_EPS,
        },
        ValueIndicator,
    },
    indicator::Indicator,
};

use super::FlowInput;

const DEFAULT_WINDOW: usize = 60;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FlowFactorKind {
    LwmaLogretSum5103050,
    MidDevFromMean10,
    HlRatioQuantileSpread10,
    VwapOverMeanClose15,
    NegVwRet10,
    MaxRet5,
    Top20pctVolRetVarW,
    PosRetSumOnVolSpikeW,
    PosRetVolatility20,
    VwapHighweightMinusVwapAllW,
    NegVolatilityOfPosret10,
    StdHlRatio10,
    MeanSellPriceOverClose10,
    TypicalPriceBollingerZ,
    NegCumret40,
    RetMinusYdaySameMinuteMinusMean20,
    UpperShadowStd40,
    StdHlRatio40,
    LowerShadowStd40,
    CorrRet1mTvr20,
    NegCorrDiffTvr1DiffClose120,
    OrderbookVolumeImbalance1m,
    StdMidp11riserate50,
    StdVol50,
    InvSpread1,
    StdDiffratioTwap550,
    CumOfiRatio,
    TwapMidDev,
    MeanVol20,
    VolCv50,
    BidDepthVolatilityCancelRate,
    NegMeanMidp11riserate10030MulMeanVol30,
    CorrCumvolAbv5mean20,
}

impl FlowFactorKind {
    pub const ALL: &'static [FlowFactorKind] = &[
        FlowFactorKind::LwmaLogretSum5103050,
        FlowFactorKind::MidDevFromMean10,
        FlowFactorKind::HlRatioQuantileSpread10,
        FlowFactorKind::VwapOverMeanClose15,
        FlowFactorKind::NegVwRet10,
        FlowFactorKind::MaxRet5,
        FlowFactorKind::Top20pctVolRetVarW,
        FlowFactorKind::PosRetSumOnVolSpikeW,
        FlowFactorKind::PosRetVolatility20,
        FlowFactorKind::VwapHighweightMinusVwapAllW,
        FlowFactorKind::NegVolatilityOfPosret10,
        FlowFactorKind::StdHlRatio10,
        FlowFactorKind::MeanSellPriceOverClose10,
        FlowFactorKind::TypicalPriceBollingerZ,
        FlowFactorKind::NegCumret40,
        FlowFactorKind::RetMinusYdaySameMinuteMinusMean20,
        FlowFactorKind::UpperShadowStd40,
        FlowFactorKind::StdHlRatio40,
        FlowFactorKind::LowerShadowStd40,
        FlowFactorKind::CorrRet1mTvr20,
        FlowFactorKind::NegCorrDiffTvr1DiffClose120,
        FlowFactorKind::OrderbookVolumeImbalance1m,
        FlowFactorKind::StdMidp11riserate50,
        FlowFactorKind::StdVol50,
        FlowFactorKind::InvSpread1,
        FlowFactorKind::StdDiffratioTwap550,
        FlowFactorKind::CumOfiRatio,
        FlowFactorKind::TwapMidDev,
        FlowFactorKind::MeanVol20,
        FlowFactorKind::VolCv50,
        FlowFactorKind::BidDepthVolatilityCancelRate,
        FlowFactorKind::NegMeanMidp11riserate10030MulMeanVol30,
        FlowFactorKind::CorrCumvolAbv5mean20,
    ];

    #[must_use]
    pub fn as_str(&self) -> &'static str {
        match self {
            FlowFactorKind::LwmaLogretSum5103050 => "lwma_logret_sum_5_10_30_50",
            FlowFactorKind::MidDevFromMean10 => "mid_dev_from_mean_10",
            FlowFactorKind::HlRatioQuantileSpread10 => "hl_ratio_quantile_spread_10",
            FlowFactorKind::VwapOverMeanClose15 => "vwap_over_mean_close_15",
            FlowFactorKind::NegVwRet10 => "neg_vw_ret_10",
            FlowFactorKind::MaxRet5 => "max_ret_5",
            FlowFactorKind::Top20pctVolRetVarW => "top20pct_vol_ret_var_W",
            FlowFactorKind::PosRetSumOnVolSpikeW => "pos_ret_sum_on_vol_spike_W",
            FlowFactorKind::PosRetVolatility20 => "pos_ret_volatility_20",
            FlowFactorKind::VwapHighweightMinusVwapAllW => "vwap_highweight_minus_vwap_all_W",
            FlowFactorKind::NegVolatilityOfPosret10 => "neg_volatility_of_posret_10",
            FlowFactorKind::StdHlRatio10 => "std_hl_ratio_10",
            FlowFactorKind::MeanSellPriceOverClose10 => "mean_sell_price_over_close_10",
            FlowFactorKind::TypicalPriceBollingerZ => "typical_price_bollinger_z",
            FlowFactorKind::NegCumret40 => "neg_cumret_40",
            FlowFactorKind::RetMinusYdaySameMinuteMinusMean20 => {
                "ret_minus_yday_same_minute_minus_mean20"
            }
            FlowFactorKind::UpperShadowStd40 => "upper_shadow_std_40",
            FlowFactorKind::StdHlRatio40 => "std_hl_ratio_40",
            FlowFactorKind::LowerShadowStd40 => "lower_shadow_std_40",
            FlowFactorKind::CorrRet1mTvr20 => "corr_ret1m_tvr_20",
            FlowFactorKind::NegCorrDiffTvr1DiffClose120 => "neg_corr_diff_tvr1_diff_close1_20",
            FlowFactorKind::OrderbookVolumeImbalance1m => "orderbook_volume_imbalance_1m",
            FlowFactorKind::StdMidp11riserate50 => "std_midp11riserate_50",
            FlowFactorKind::StdVol50 => "std_vol_50",
            FlowFactorKind::InvSpread1 => "inv_spread_1",
            FlowFactorKind::StdDiffratioTwap550 => "std_diffratio_twap_5_50",
            FlowFactorKind::CumOfiRatio => "cum_ofi_ratio",
            FlowFactorKind::TwapMidDev => "twap_mid_dev",
            FlowFactorKind::MeanVol20 => "mean_vol_20",
            FlowFactorKind::VolCv50 => "vol_cv_50",
            FlowFactorKind::BidDepthVolatilityCancelRate => "bid_depth_volatility_cancel_rate",
            FlowFactorKind::NegMeanMidp11riserate10030MulMeanVol30 => {
                "neg_mean_midp11riserate_100_30_mul_mean_vol_30"
            }
            FlowFactorKind::CorrCumvolAbv5mean20 => "corr_cumvol_abv5mean_20",
        }
    }

    #[must_use]
    pub fn default_window(&self) -> usize {
        match self {
            FlowFactorKind::MidDevFromMean10
            | FlowFactorKind::HlRatioQuantileSpread10
            | FlowFactorKind::NegVwRet10
            | FlowFactorKind::StdHlRatio10
            | FlowFactorKind::MeanSellPriceOverClose10
            | FlowFactorKind::NegVolatilityOfPosret10 => 10,
            FlowFactorKind::VwapOverMeanClose15 => 15,
            FlowFactorKind::PosRetVolatility20
            | FlowFactorKind::CorrRet1mTvr20
            | FlowFactorKind::NegCorrDiffTvr1DiffClose120
            | FlowFactorKind::MeanVol20
            | FlowFactorKind::CorrCumvolAbv5mean20 => 20,
            FlowFactorKind::NegCumret40
            | FlowFactorKind::UpperShadowStd40
            | FlowFactorKind::StdHlRatio40
            | FlowFactorKind::LowerShadowStd40 => 40,
            FlowFactorKind::StdMidp11riserate50
            | FlowFactorKind::StdVol50
            | FlowFactorKind::StdDiffratioTwap550
            | FlowFactorKind::VolCv50 => 50,
            FlowFactorKind::MaxRet5 => 5,
            FlowFactorKind::TypicalPriceBollingerZ => 20,
            FlowFactorKind::RetMinusYdaySameMinuteMinusMean20 => 20,
            FlowFactorKind::NegMeanMidp11riserate10030MulMeanVol30 => 30,
            FlowFactorKind::LwmaLogretSum5103050 => 50,
            _ => DEFAULT_WINDOW,
        }
    }

    #[must_use]
    pub fn secondary_window(&self) -> usize {
        match self {
            FlowFactorKind::NegMeanMidp11riserate10030MulMeanVol30 => 30,
            _ => self.default_window(),
        }
    }
}

#[derive(Debug)]
pub struct FlowFactor {
    kind: FlowFactorKind,
    value: f64,
    count: usize,
    initialized: bool,
    has_inputs: bool,
    window: usize,
    window_secondary: usize,
    rolling_a: RollingWindow,
    rolling_b: RollingWindow,
    rolling_c: RollingWindow,
    rolling_d: RollingWindow,
    corr_a: RollingCorrelation,
    lag_a: LagBuffer,
    lag_b: LagBuffer,
    lwma_5: RollingLWMA,
    lwma_10: RollingLWMA,
    lwma_30: RollingLWMA,
    lwma_50: RollingLWMA,
    last_close: Option<f64>,
    last_volume: Option<f64>,
    last_turnover: Option<f64>,
    last_twap: Option<f64>,
}

impl FlowFactor {
    #[must_use]
    pub fn new(kind: FlowFactorKind) -> Self {
        let window = kind.default_window();
        let window_secondary = kind.secondary_window();
        let lag_a = match kind {
            FlowFactorKind::RetMinusYdaySameMinuteMinusMean20 => 1440,
            _ => 1,
        };
        Self {
            kind,
            value: 0.0,
            count: 0,
            initialized: false,
            has_inputs: false,
            window,
            window_secondary,
            rolling_a: RollingWindow::new(window),
            rolling_b: RollingWindow::new(window_secondary),
            rolling_c: RollingWindow::new(window),
            rolling_d: RollingWindow::new(window),
            corr_a: RollingCorrelation::new(window),
            lag_a: LagBuffer::new(lag_a),
            lag_b: LagBuffer::new(5),
            lwma_5: RollingLWMA::new(5),
            lwma_10: RollingLWMA::new(10),
            lwma_30: RollingLWMA::new(30),
            lwma_50: RollingLWMA::new(50),
            last_close: None,
            last_volume: None,
            last_turnover: None,
            last_twap: None,
        }
    }

    pub fn update(&mut self, input: &FlowInput) {
        let close = input.close;
        let ret = input.ret.or_else(|| {
            if let (Some(close), Some(prev)) = (close, self.last_close) {
                Some(safe_div(close - prev, prev, DEFAULT_EPS))
            } else {
                None
            }
        });
        let logret = input.logret.or_else(|| {
            if let (Some(close), Some(prev)) = (close, self.last_close) {
                Some(safe_div(close, prev, DEFAULT_EPS).ln())
            } else {
                None
            }
        });

        self.count += 1;
        self.has_inputs = true;

        match self.kind {
            FlowFactorKind::LwmaLogretSum5103050 => {
                if let Some(lr) = logret {
                    self.lwma_5.push(lr);
                    self.lwma_10.push(lr);
                    self.lwma_30.push(lr);
                    self.lwma_50.push(lr);
                    self.value = self.lwma_5.value()
                        + self.lwma_10.value()
                        + self.lwma_30.value()
                        + self.lwma_50.value();
                    self.initialized = self.lwma_50.is_full();
                }
            }
            FlowFactorKind::MidDevFromMean10 => {
                if let Some(mid) = input.mid_price {
                    self.rolling_a.push(mid);
                    let mean = self.rolling_a.mean();
                    self.value = safe_div(mean - mid, mean + DEFAULT_EPS, DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::HlRatioQuantileSpread10 => {
                if let (Some(high), Some(low)) = (input.high, input.low) {
                    let ratio = safe_div(high, low, DEFAULT_EPS);
                    self.rolling_a.push(ratio);
                    let q_hi = self.rolling_a.quantile(0.8);
                    let q_lo = self.rolling_a.quantile(0.2);
                    self.value = q_hi - q_lo;
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::VwapOverMeanClose15 => {
                if let (Some(vol), Some(close)) = (input.volume, close) {
                    self.rolling_a.push(vol * close);
                    self.rolling_b.push(vol);
                    self.rolling_c.push(close);
                    let vwap = safe_div(self.rolling_a.mean(), self.rolling_b.mean(), DEFAULT_EPS);
                    self.value = safe_div(vwap, self.rolling_c.mean(), DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::NegVwRet10 => {
                if let (Some(vol), Some(ret)) = (input.volume, ret) {
                    self.rolling_a.push(vol * ret);
                    self.rolling_b.push(vol);
                    let num = self.rolling_a.mean();
                    let den = self.rolling_b.mean();
                    self.value = -safe_div(num, den, DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::MaxRet5 => {
                if let Some(ret) = ret {
                    self.rolling_a.push(ret);
                    self.value = self.rolling_a.max();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::Top20pctVolRetVarW => {
                if let (Some(vol), Some(ret)) = (input.volume, ret) {
                    self.rolling_a.push(vol);
                    self.rolling_b.push(ret);
                    let q = self.rolling_a.quantile(0.8);
                    let mut filtered = Vec::new();
                    for (v, r) in self.rolling_a.values().iter().zip(self.rolling_b.values()) {
                        if *v >= q {
                            filtered.push(*r);
                        }
                    }
                    let var = if filtered.is_empty() {
                        0.0
                    } else {
                        let mu = mean(&filtered);
                        let sum = filtered.iter().map(|x| (x - mu) * (x - mu)).sum::<f64>();
                        safe_div(sum, filtered.len() as f64, DEFAULT_EPS)
                    };
                    self.value = var;
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::PosRetSumOnVolSpikeW => {
                if let (Some(vol), Some(ret)) = (input.volume, ret) {
                    self.rolling_a.push(vol);
                    let mean = self.rolling_a.mean();
                    let std = self.rolling_a.std();
                    let flag = if vol > mean + std && ret > 0.0 { ret } else { 0.0 };
                    self.rolling_b.push(flag);
                    self.value = self.rolling_b.sum();
                    self.initialized = self.rolling_b.is_full();
                }
            }
            FlowFactorKind::PosRetVolatility20 => {
                if let Some(ret) = ret {
                    self.rolling_a.push(ret);
                    let pos: Vec<f64> = self
                        .rolling_a
                        .values()
                        .iter()
                        .copied()
                        .filter(|v| *v > 0.0)
                        .collect();
                    let var = if pos.is_empty() {
                        0.0
                    } else {
                        let mu = mean(&pos);
                        let sum = pos.iter().map(|x| (x - mu) * (x - mu)).sum::<f64>();
                        safe_div(sum, pos.len() as f64, DEFAULT_EPS)
                    };
                    self.value = var.sqrt();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::VwapHighweightMinusVwapAllW => {
                if let (Some(vol), Some(close), Some(ret)) = (input.volume, close, ret) {
                    let weight = ret.abs();
                    self.rolling_a.push(vol * close * weight);
                    self.rolling_b.push(vol * weight);
                    self.rolling_c.push(vol * close);
                    self.rolling_d.push(vol);
                    let weighted = safe_div(self.rolling_a.sum(), self.rolling_b.sum(), DEFAULT_EPS);
                    let all = safe_div(self.rolling_c.sum(), self.rolling_d.sum(), DEFAULT_EPS);
                    self.value = weighted - all;
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::NegVolatilityOfPosret10 => {
                if let Some(ret) = ret {
                    self.rolling_a.push(ret);
                    let pos: Vec<f64> = self
                        .rolling_a
                        .values()
                        .iter()
                        .copied()
                        .filter(|v| *v > 0.0)
                        .collect();
                    let var = if pos.is_empty() {
                        0.0
                    } else {
                        let mu = mean(&pos);
                        let sum = pos.iter().map(|x| (x - mu) * (x - mu)).sum::<f64>();
                        safe_div(sum, pos.len() as f64, DEFAULT_EPS)
                    };
                    self.value = -var.sqrt();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::StdHlRatio10 => {
                if let (Some(high), Some(low)) = (input.high, input.low) {
                    let ratio = safe_div(high, low, DEFAULT_EPS);
                    self.rolling_a.push(ratio);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::MeanSellPriceOverClose10 => {
                if let Some(close) = close {
                    let sell = input.sell_vwap.unwrap_or(close);
                    self.rolling_a.push(sell);
                    self.rolling_b.push(close);
                    self.value = safe_div(self.rolling_a.mean(), self.rolling_b.mean(), DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::TypicalPriceBollingerZ => {
                if let (Some(high), Some(low), Some(close)) = (input.high, input.low, close) {
                    let typical = safe_div(high + low + close, 3.0, DEFAULT_EPS);
                    self.rolling_a.push(typical);
                    let mean = self.rolling_a.mean();
                    let std = self.rolling_a.std();
                    self.value = safe_div(typical - mean, std, DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::NegCumret40 => {
                if let Some(ret) = ret {
                    self.rolling_a.push(ret);
                    self.value = -self.rolling_a.sum();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::RetMinusYdaySameMinuteMinusMean20 => {
                if let Some(ret) = ret {
                    let lag_ret = self.lag_a.push(ret).unwrap_or(0.0);
                    self.rolling_a.push(ret);
                    let mean = self.rolling_a.mean();
                    self.value = ret - lag_ret - mean;
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::UpperShadowStd40 => {
                if let (Some(open), Some(high), Some(low), Some(close)) =
                    (input.open, input.high, input.low, close)
                {
                    let upper = safe_div(high - open.max(close), high - low + DEFAULT_EPS, DEFAULT_EPS);
                    self.rolling_a.push(upper);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::StdHlRatio40 => {
                if let (Some(high), Some(low)) = (input.high, input.low) {
                    let ratio = safe_div(high, low, DEFAULT_EPS);
                    self.rolling_a.push(ratio);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::LowerShadowStd40 => {
                if let (Some(open), Some(high), Some(low), Some(close)) =
                    (input.open, input.high, input.low, close)
                {
                    let lower = safe_div(open.min(close) - low, high - low + DEFAULT_EPS, DEFAULT_EPS);
                    self.rolling_a.push(lower);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::CorrRet1mTvr20 => {
                if let (Some(ret), Some(tvr)) = (ret, input.turnover) {
                    self.corr_a.push(ret, tvr);
                    self.value = self.corr_a.corr();
                    self.initialized = self.corr_a.is_full();
                }
            }
            FlowFactorKind::NegCorrDiffTvr1DiffClose120 => {
                if let (Some(tvr), Some(close)) = (input.turnover, close) {
                    if let (Some(prev_tvr), Some(prev_close)) = (self.last_turnover, self.last_close)
                    {
                        let diff_tvr = diff_ratio(tvr, prev_tvr);
                        let diff_close = diff_ratio(close, prev_close);
                        self.corr_a.push(diff_tvr, diff_close);
                        self.value = -self.corr_a.corr();
                        self.initialized = self.corr_a.is_full();
                    }
                    self.last_turnover = Some(tvr);
                }
            }
            FlowFactorKind::OrderbookVolumeImbalance1m => {
                if let (Some(bid), Some(ask)) = (input.bidvol, input.askvol) {
                    self.value = safe_div(bid - ask, bid + ask, DEFAULT_EPS);
                    self.initialized = true;
                }
            }
            FlowFactorKind::StdMidp11riserate50 => {
                if let Some(rate) = input.midp11riserate {
                    self.rolling_a.push(rate);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::StdVol50 => {
                if let Some(vol) = input.volume {
                    self.rolling_a.push(vol);
                    self.value = self.rolling_a.std();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::InvSpread1 => {
                if let (Some(bid), Some(ask)) = (input.bid_price, input.ask_price) {
                    self.value = safe_div(1.0, ask - bid + DEFAULT_EPS, DEFAULT_EPS);
                    self.initialized = true;
                }
            }
            FlowFactorKind::StdDiffratioTwap550 => {
                if let Some(twap) = input.twap {
                    if let Some(prev) = self.lag_b.push(twap) {
                        let diff = diff_ratio(twap, prev);
                        self.rolling_a.push(diff);
                        self.value = self.rolling_a.std();
                        self.initialized = self.rolling_a.is_full();
                    }
                }
            }
            FlowFactorKind::CumOfiRatio => {
                if let (Some(bid), Some(ask)) = (input.cumbid, input.cumask) {
                    self.value = safe_div(bid - ask, bid + ask, DEFAULT_EPS);
                    self.initialized = true;
                }
            }
            FlowFactorKind::TwapMidDev => {
                if let (Some(twap), Some(mid)) = (input.twap, input.mid_price) {
                    self.value = safe_div(twap - mid, mid, DEFAULT_EPS);
                    self.initialized = true;
                }
            }
            FlowFactorKind::MeanVol20 => {
                if let Some(vol) = input.volume {
                    self.rolling_a.push(vol);
                    self.value = self.rolling_a.mean();
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::VolCv50 => {
                if let Some(vol) = input.volume {
                    self.rolling_a.push(vol);
                    let std = self.rolling_a.std();
                    let mean = self.rolling_a.mean();
                    self.value = safe_div(std, mean, DEFAULT_EPS);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::BidDepthVolatilityCancelRate => {
                if let Some(vol) = input.volume {
                    self.rolling_a.push(vol);
                    let std = self.rolling_a.std();
                    let cancel = if let Some(prev) = self.last_volume {
                        if vol < prev { 1.0 } else { 0.0 }
                    } else {
                        0.0
                    };
                    self.rolling_b.push(cancel);
                    let cancel_rate = safe_div(self.rolling_b.sum(), self.rolling_b.len() as f64, DEFAULT_EPS);
                    self.value = std * cancel_rate;
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::NegMeanMidp11riserate10030MulMeanVol30 => {
                if let (Some(rate), Some(vol)) = (input.midp11riserate_100, input.volume) {
                    self.rolling_a.push(rate);
                    self.rolling_b.push(vol);
                    let mean_rate = self.rolling_a.mean();
                    let mean_vol = self.rolling_b.mean();
                    self.value = -(mean_rate * mean_vol);
                    self.initialized = self.rolling_a.is_full();
                }
            }
            FlowFactorKind::CorrCumvolAbv5mean20 => {
                if let (Some(cumvol), Some(abv5)) = (input.cumvol, input.abv5mean) {
                    self.corr_a.push(cumvol, abv5);
                    self.value = self.corr_a.corr();
                    self.initialized = self.corr_a.is_full();
                }
            }
        }

        if let Some(close) = close {
            self.last_close = Some(close);
        }
        if let Some(vol) = input.volume {
            self.last_volume = Some(vol);
        }
        if let Some(twap) = input.twap {
            self.last_twap = Some(twap);
        }
    }
}

impl Display for FlowFactor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}()", self.name())
    }
}

impl Indicator for FlowFactor {
    fn name(&self) -> String {
        self.kind.as_str().to_string()
    }

    fn has_inputs(&self) -> bool {
        self.has_inputs
    }

    fn initialized(&self) -> bool {
        self.initialized
    }

    fn handle_bar(&mut self, bar: &Bar) {
        let input = FlowInput::from_bar(bar);
        self.update(&input);
    }

    fn reset(&mut self) {
        *self = Self::new(self.kind);
    }
}

impl ValueIndicator for FlowFactor {
    fn value(&self) -> f64 {
        self.value
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_input() -> FlowInput {
        let mut input = FlowInput::default();
        input.open = Some(100.0);
        input.high = Some(102.0);
        input.low = Some(99.0);
        input.close = Some(101.0);
        input.volume = Some(5.0);
        input.ret = Some(0.001);
        input.logret = Some(0.001);
        input.mid_price = Some(100.5);
        input.vwap = Some(100.8);
        input.twap = Some(100.7);
        input.turnover = Some(1000.0);
        input.bid_price = Some(100.0);
        input.ask_price = Some(101.0);
        input.cumbid = Some(50.0);
        input.cumask = Some(45.0);
        input.cumvol = Some(100.0);
        input.abv5mean = Some(95.0);
        input.midp11riserate = Some(0.2);
        input.midp11riserate_100 = Some(0.1);
        input.sell_vwap = Some(100.9);
        input.bidvol = Some(60.0);
        input.askvol = Some(40.0);
        input
    }

    #[test]
    fn test_flow_factor_updates_all_kinds() {
        let input = sample_input();
        for kind in FlowFactorKind::ALL {
            let mut factor = FlowFactor::new(*kind);
            factor.update(&input);
            assert!(factor.has_inputs());
            assert!(factor.value().is_finite());
        }
    }

    #[test]
    fn test_flow_factor_name_matches() {
        let factor = FlowFactor::new(FlowFactorKind::MaxRet5);
        assert_eq!(factor.name(), "max_ret_5");
        assert_eq!(format!("{factor}"), "max_ret_5()");
    }
}
