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

use crate::aurora_indicators::utils::{safe_div, DEFAULT_EPS};

mod prelude;
mod state;
#[cfg(test)]
mod test_utils;
mod sigma_volatility;
mod bid_imbalance_change;
mod net_order_flow;
mod top1_depth_imbalance;
mod depth_ratio_5;
mod spread_ratio;
mod bid_volume_diff_rate;
mod book_liquidity_inv;
mod midprice_volatility;
mod bid1_impact_price;
mod ask_skew_price_weighted;
mod depth_weighted_deviation;
mod lp_up_ticks_volume_sum;
mod ret_var_1m;
mod order_flow_direction;
mod depth_spread_5ask_bid;
mod corr_price_volume;
mod corr_return_volume_lag;
mod vwap_mid_diff;
mod top30_volume_ret_var;
mod volume_ret_corr_lead;
mod amihud_illiquidity;
mod deep_order_count;
mod log_factor_ret;
mod tvr_metrics;
mod volume_stat_features;
mod orderbook_slope_bid;
mod return_ar1;
mod net_top3_pressure;
mod book_pressure_gradient;
mod orderbook_convexity_bid;
mod weighted_mid_spread_ratio;
mod orderbook_entropy;
mod depth_decay_ratio;
mod ask_impact_volatility;
mod quote_count_variation;
mod cross_depth_ratio;
mod reverse_tick_ratio;
mod dominant_side_tvr;
mod deep_ask_pressure;
mod vpin_order_flow;
mod bid_slope;
mod ask_weighted_ir;
mod micro_return_std;
mod order_spread_ir;
mod return_duration_skew;
mod orderbook_crowding_ratio;
mod ask_shield_ratio;
mod bid_sweep_ratio;
mod order_imbalance_std;
mod cross_spread_depth;
mod ask_ladder_density;
mod pullback_ratio;
mod lastprice_jump_freq;
mod spread_skew;
mod center_of_liquidity_bid;
mod liquidity_gradient_ratio;
mod order_age_indicator;
mod ask_pressure_zone_ratio;
mod volume_density_per_spread;
mod tick_direction_entropy;
mod tick_price_range_ratio;
mod first_level_shift_rate;
mod ask_slope_level_weighted;
mod orderbook_tilt;
mod quote_reversion_speed;
mod volatility_skew;
mod volume_spike_score;
mod mid_price_drift;
mod top1_ask_absorption_rate;
mod book_compression_rate;
mod volume_direction_consistency;
mod price_jump_entropy;
mod ret_vpin_diff;
mod ask_bulge_index;
mod resistance_test_count;
mod trend_acceleration;
mod volume_saturation;
mod orderbook_breathing_rate;
mod quote_crossing_score;
mod volume_impact_ratio;
mod orderstack_asymmetry;
mod mean_spread_reversal;
mod burst_recovery_ratio;
mod ret_momentum_ratio;
mod hidden_order_inference;
mod liquidity_vacuum_score;
mod lastprice_mid_mirror_score;
mod volume_spike_count;
mod lvl5_avg_price_ratio_sum;
mod lvl5_avg_price_ratio_sum_std;
mod lvl5_avg_price_ratio_sum_ir;
mod lvl5_avg_price_ratio_sum_skew;
mod lvl5_avg_price_ratio_sum_kurtosis;
mod trade_price_above_ask1_ratio;
mod trade_price_below_bid1_ratio;
mod corr_buy5avg_over_bid1_vs_ask5avg_over_ask1;
mod corr_buy5avg_vs_ask5avg;
mod mid_over_buy5avg_ratio;
mod orderbook_volume_imbalance_l;
mod orderbook_amount_imbalance_std_l;
mod orderbook_amount_imbalance_norm_mean_l;
mod bid_quote_slope_stats;
mod ask_quote_slope_stats;
mod bid_price_reg_r2_stats;
mod ask_price_reg_r2_stats;
mod ask_reg_residual_stats;
mod bid_reg_residual_stats;
mod ofi_cum_l;
mod log_price_slope_l;
mod trade_penetration_level_diff;
mod hidden_order_ratio_penetrated;

pub use sigma_volatility::SigmaVolatility;
pub use bid_imbalance_change::BidImbalanceChange;
pub use net_order_flow::NetOrderFlow;
pub use top1_depth_imbalance::Top1DepthImbalance;
pub use depth_ratio_5::DepthRatio5;
pub use spread_ratio::SpreadRatio;
pub use bid_volume_diff_rate::BidVolumeDiffRate;
pub use book_liquidity_inv::BookLiquidityInv;
pub use midprice_volatility::MidpriceVolatility;
pub use bid1_impact_price::Bid1ImpactPrice;
pub use ask_skew_price_weighted::AskSkewPriceWeighted;
pub use depth_weighted_deviation::DepthWeightedDeviation;
pub use lp_up_ticks_volume_sum::LpUpTicksVolumeSum;
pub use ret_var_1m::RetVar1m;
pub use order_flow_direction::OrderFlowDirection;
pub use depth_spread_5ask_bid::DepthSpread5askBid;
pub use corr_price_volume::CorrPriceVolume;
pub use corr_return_volume_lag::CorrReturnVolumeLag;
pub use vwap_mid_diff::VwapMidDiff;
pub use top30_volume_ret_var::Top30VolumeRetVar;
pub use volume_ret_corr_lead::VolumeRetCorrLead;
pub use amihud_illiquidity::AmihudIlliquidity;
pub use deep_order_count::DeepOrderCount;
pub use log_factor_ret::LogFactorRet;
pub use tvr_metrics::TvrMetrics;
pub use volume_stat_features::VolumeStatFeatures;
pub use orderbook_slope_bid::OrderbookSlopeBid;
pub use return_ar1::ReturnAr1;
pub use net_top3_pressure::NetTop3Pressure;
pub use book_pressure_gradient::BookPressureGradient;
pub use orderbook_convexity_bid::OrderbookConvexityBid;
pub use weighted_mid_spread_ratio::WeightedMidSpreadRatio;
pub use orderbook_entropy::OrderbookEntropy;
pub use depth_decay_ratio::DepthDecayRatio;
pub use ask_impact_volatility::AskImpactVolatility;
pub use quote_count_variation::QuoteCountVariation;
pub use cross_depth_ratio::CrossDepthRatio;
pub use reverse_tick_ratio::ReverseTickRatio;
pub use dominant_side_tvr::DominantSideTvr;
pub use deep_ask_pressure::DeepAskPressure;
pub use vpin_order_flow::VpinOrderFlow;
pub use bid_slope::BidSlope;
pub use ask_weighted_ir::AskWeightedIr;
pub use micro_return_std::MicroReturnStd;
pub use order_spread_ir::OrderSpreadIr;
pub use return_duration_skew::ReturnDurationSkew;
pub use orderbook_crowding_ratio::OrderbookCrowdingRatio;
pub use ask_shield_ratio::AskShieldRatio;
pub use bid_sweep_ratio::BidSweepRatio;
pub use order_imbalance_std::OrderImbalanceStd;
pub use cross_spread_depth::CrossSpreadDepth;
pub use ask_ladder_density::AskLadderDensity;
pub use pullback_ratio::PullbackRatio;
pub use lastprice_jump_freq::LastpriceJumpFreq;
pub use spread_skew::SpreadSkew;
pub use center_of_liquidity_bid::CenterOfLiquidityBid;
pub use liquidity_gradient_ratio::LiquidityGradientRatio;
pub use order_age_indicator::OrderAgeIndicator;
pub use ask_pressure_zone_ratio::AskPressureZoneRatio;
pub use volume_density_per_spread::VolumeDensityPerSpread;
pub use tick_direction_entropy::TickDirectionEntropy;
pub use tick_price_range_ratio::TickPriceRangeRatio;
pub use first_level_shift_rate::FirstLevelShiftRate;
pub use ask_slope_level_weighted::AskSlopeLevelWeighted;
pub use orderbook_tilt::OrderbookTilt;
pub use quote_reversion_speed::QuoteReversionSpeed;
pub use volatility_skew::VolatilitySkew;
pub use volume_spike_score::VolumeSpikeScore;
pub use mid_price_drift::MidPriceDrift;
pub use top1_ask_absorption_rate::Top1AskAbsorptionRate;
pub use book_compression_rate::BookCompressionRate;
pub use volume_direction_consistency::VolumeDirectionConsistency;
pub use price_jump_entropy::PriceJumpEntropy;
pub use ret_vpin_diff::RetVpinDiff;
pub use ask_bulge_index::AskBulgeIndex;
pub use resistance_test_count::ResistanceTestCount;
pub use trend_acceleration::TrendAcceleration;
pub use volume_saturation::VolumeSaturation;
pub use orderbook_breathing_rate::OrderbookBreathingRate;
pub use quote_crossing_score::QuoteCrossingScore;
pub use volume_impact_ratio::VolumeImpactRatio;
pub use orderstack_asymmetry::OrderstackAsymmetry;
pub use mean_spread_reversal::MeanSpreadReversal;
pub use burst_recovery_ratio::BurstRecoveryRatio;
pub use ret_momentum_ratio::RetMomentumRatio;
pub use hidden_order_inference::HiddenOrderInference;
pub use liquidity_vacuum_score::LiquidityVacuumScore;
pub use lastprice_mid_mirror_score::LastpriceMidMirrorScore;
pub use volume_spike_count::VolumeSpikeCount;
pub use lvl5_avg_price_ratio_sum::Lvl5AvgPriceRatioSum;
pub use lvl5_avg_price_ratio_sum_std::Lvl5AvgPriceRatioSumStd;
pub use lvl5_avg_price_ratio_sum_ir::Lvl5AvgPriceRatioSumIr;
pub use lvl5_avg_price_ratio_sum_skew::Lvl5AvgPriceRatioSumSkew;
pub use lvl5_avg_price_ratio_sum_kurtosis::Lvl5AvgPriceRatioSumKurtosis;
pub use trade_price_above_ask1_ratio::TradePriceAboveAsk1Ratio;
pub use trade_price_below_bid1_ratio::TradePriceBelowBid1Ratio;
pub use corr_buy5avg_over_bid1_vs_ask5avg_over_ask1::CorrBuy5avgOverBid1VsAsk5avgOverAsk1;
pub use corr_buy5avg_vs_ask5avg::CorrBuy5avgVsAsk5avg;
pub use mid_over_buy5avg_ratio::MidOverBuy5avgRatio;
pub use orderbook_volume_imbalance_l::OrderbookVolumeImbalanceL;
pub use orderbook_amount_imbalance_std_l::OrderbookAmountImbalanceStdL;
pub use orderbook_amount_imbalance_norm_mean_l::OrderbookAmountImbalanceNormMeanL;
pub use bid_quote_slope_stats::BidQuoteSlopeStats;
pub use ask_quote_slope_stats::AskQuoteSlopeStats;
pub use bid_price_reg_r2_stats::BidPriceRegR2Stats;
pub use ask_price_reg_r2_stats::AskPriceRegR2Stats;
pub use ask_reg_residual_stats::AskRegResidualStats;
pub use bid_reg_residual_stats::BidRegResidualStats;
pub use ofi_cum_l::OfiCumL;
pub use log_price_slope_l::LogPriceSlopeL;
pub use trade_penetration_level_diff::TradePenetrationLevelDiff;
pub use hidden_order_ratio_penetrated::HiddenOrderRatioPenetrated;

#[inline]
pub(super) fn sum_range(values: &[f64], start: usize, end: usize) -> f64 {
    values
        .iter()
        .enumerate()
        .filter(|(idx, _)| *idx >= start && *idx < end)
        .map(|(_, val)| val)
        .sum()
}

#[inline]
pub(super) fn avg_range(values: &[f64], start: usize, end: usize) -> f64 {
    let end = end.min(values.len());
    if start >= end {
        return 0.0;
    }
    let slice = &values[start..end];
    safe_div(slice.iter().sum::<f64>(), slice.len() as f64, DEFAULT_EPS)
}

#[inline]
pub(super) fn fill_book_levels(
    book: &nautilus_model::orderbook::OrderBook,
    bid_prices: &mut [f64; crate::aurora_indicators::book::BOOK_LEVELS],
    bid_sizes: &mut [f64; crate::aurora_indicators::book::BOOK_LEVELS],
    ask_prices: &mut [f64; crate::aurora_indicators::book::BOOK_LEVELS],
    ask_sizes: &mut [f64; crate::aurora_indicators::book::BOOK_LEVELS],
) {
    bid_prices.fill(0.0);
    bid_sizes.fill(0.0);
    ask_prices.fill(0.0);
    ask_sizes.fill(0.0);

    for (idx, level) in book
        .bids(Some(crate::aurora_indicators::book::BOOK_LEVELS))
        .enumerate()
    {
        if idx >= crate::aurora_indicators::book::BOOK_LEVELS {
            break;
        }
        bid_prices[idx] = level.price.value.as_f64();
        bid_sizes[idx] = level.size();
    }
    for (idx, level) in book
        .asks(Some(crate::aurora_indicators::book::BOOK_LEVELS))
        .enumerate()
    {
        if idx >= crate::aurora_indicators::book::BOOK_LEVELS {
            break;
        }
        ask_prices[idx] = level.price.value.as_f64();
        ask_sizes[idx] = level.size();
    }
}

#[inline]
pub(super) fn mid_and_spread(
    book: &nautilus_model::orderbook::OrderBook,
) -> (Option<f64>, Option<f64>) {
    if let (Some(bid), Some(ask)) = (book.best_bid_price(), book.best_ask_price()) {
        let bid = bid.as_f64();
        let ask = ask.as_f64();
        (Some((bid + ask) * 0.5), Some(ask - bid))
    } else {
        (None, None)
    }
}

#[inline]
pub(super) fn sum_depth(values: &[f64], depth: usize) -> f64 {
    values.iter().take(depth.min(values.len())).sum()
}

#[inline]
pub(super) fn notional_sum(prices: &[f64], sizes: &[f64], depth: usize) -> f64 {
    prices
        .iter()
        .zip(sizes.iter())
        .take(depth.min(prices.len()).min(sizes.len()))
        .map(|(p, q)| p * q)
        .sum()
}

#[inline]
pub(super) fn index_array<const N: usize>() -> [f64; N] {
    std::array::from_fn(|i| i as f64)
}
