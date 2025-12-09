// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing.permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------
//! Regime-aware risk advisories (volatility shocks, trend/chaos gating, inventory hedges).
//!
//! The Rust side owns the full state machine so the Python strategy only consumes decisions.

/// Risk modes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskMode {
    Full,
    NormalOnly,
}

impl RiskMode {
    /// Build from a user-facing string.
    #[must_use]
    pub fn from_str(mode: &str) -> Option<Self> {
        match mode.to_ascii_lowercase().as_str() {
            "full" => Some(Self::Full),
            "normal_only" => Some(Self::NormalOnly),
            _ => None,
        }
    }
}

/// Coarse flow-control states for the quoting engine.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskState {
    Normal,
    Widen,
    Pause,
}

/// Regime buckets used by the strategy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegimeState {
    Normal,
    TrendUp,
    TrendDown,
    Chaos,
}

impl RegimeState {
    #[must_use]
    pub fn as_str(&self) -> &'static str {
        match self {
            RegimeState::Normal => "NORMAL",
            RegimeState::TrendUp => "TREND_UP",
            RegimeState::TrendDown => "TREND_DOWN",
            RegimeState::Chaos => "CHAOS",
        }
    }
}

/// In TREND regimes keep the with-trend side close and clip near quotes on the opposite side.
#[derive(Debug, Clone)]
pub struct TrendBias {
    pub with_trend_is_bid: bool,
    pub opposite_clip_levels: u32,
}

/// Parameters driving regime detection and how regimes translate to quoting controls.
#[derive(Debug, Clone)]
pub struct RegimeParams {
    pub alpha_gate_bps: f64,
    pub trend_delta_ratio_threshold: f64,
    pub mo_imbalance_threshold: f64,
    pub hysteresis_ns: u64,
    pub trend_opposite_clip_levels: u32,
    pub trend_widen_mult: f64,
    pub trend_reduce_levels: u32,
    pub chaos_widen_mult: f64,
    pub chaos_reduce_levels: u32,
    pub pause_on_chaos: bool,
}

impl RegimeParams {
    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn new(
        alpha_gate_bps: f64,
        trend_delta_ratio_threshold: f64,
        mo_imbalance_threshold: f64,
        hysteresis_ms: f64,
        trend_opposite_clip_levels: u32,
        trend_widen_mult: f64,
        trend_reduce_levels: u32,
        chaos_widen_mult: f64,
        chaos_reduce_levels: u32,
        pause_on_chaos: bool,
    ) -> Self {
        Self {
            alpha_gate_bps: alpha_gate_bps.abs(),
            trend_delta_ratio_threshold: trend_delta_ratio_threshold.max(0.0),
            mo_imbalance_threshold: mo_imbalance_threshold.max(0.0),
            hysteresis_ns: (hysteresis_ms.max(0.0) * 1_000_000.0).round() as u64,
            trend_opposite_clip_levels,
            trend_widen_mult: trend_widen_mult.max(1.0),
            trend_reduce_levels,
            chaos_widen_mult: chaos_widen_mult.max(1.0),
            chaos_reduce_levels,
            pause_on_chaos,
        }
    }
}

impl Default for RegimeParams {
    fn default() -> Self {
        Self::new(
            1.2,   // alpha_gate_bps
            0.6,   // trend_delta_ratio_threshold
            2.5,   // mo_imbalance_threshold
            800.0, // hysteresis_ms
            1,     // trend_opposite_clip_levels
            1.15,  // trend_widen_mult
            1,     // trend_reduce_levels
            2.0,   // chaos_widen_mult
            2,     // chaos_reduce_levels
            true,  // pause_on_chaos
        )
    }
}

#[derive(Debug, Clone)]
struct RegimeMachine {
    params: RegimeParams,
    current: RegimeState,
    pending: Option<RegimeState>,
    pending_since: u64,
}

impl RegimeMachine {
    fn new(params: RegimeParams) -> Self {
        Self {
            params,
            current: RegimeState::Normal,
            pending: None,
            pending_since: 0,
        }
    }

    fn update(
        &mut self,
        alpha_bps: f64,
        delta_ratio: f64,
        mo_imbalance: f64,
        sigma_ratio: f64,
        now_ns: u64,
        vol_shock_sigma_mult: f64,
    ) -> (RegimeState, Option<TrendBias>, Option<String>) {
        let (target, mut reason) = self.detect_target(
            alpha_bps,
            delta_ratio,
            mo_imbalance,
            sigma_ratio,
            vol_shock_sigma_mult,
        );
        let regime = self.advance(target, now_ns, matches!(target, RegimeState::Chaos));
        if regime == RegimeState::Chaos && reason.is_none() {
            reason = Some("chaos".to_string());
        }
        let bias = match regime {
            RegimeState::TrendUp => Some(TrendBias {
                with_trend_is_bid: true,
                opposite_clip_levels: self.params.trend_opposite_clip_levels,
            }),
            RegimeState::TrendDown => Some(TrendBias {
                with_trend_is_bid: false,
                opposite_clip_levels: self.params.trend_opposite_clip_levels,
            }),
            _ => None,
        };
        (regime, bias, reason)
    }

    fn detect_target(
        &self,
        alpha_bps: f64,
        delta_ratio: f64,
        mo_imbalance: f64,
        sigma_ratio: f64,
        vol_shock_sigma_mult: f64,
    ) -> (RegimeState, Option<String>) {
        if sigma_ratio >= vol_shock_sigma_mult {
            return (RegimeState::Chaos, Some("vol_shock".to_string()));
        }

        let alpha_abs = alpha_bps.abs();
        let has_trend_signal = alpha_abs > self.params.alpha_gate_bps
            && (delta_ratio >= self.params.trend_delta_ratio_threshold
                || mo_imbalance >= self.params.mo_imbalance_threshold);
        if has_trend_signal {
            let regime = if alpha_bps >= 0.0 {
                RegimeState::TrendUp
            } else {
                RegimeState::TrendDown
            };
            let reason = if mo_imbalance >= self.params.mo_imbalance_threshold {
                "mo_imbalance"
            } else if delta_ratio >= self.params.trend_delta_ratio_threshold {
                "delta_ratio"
            } else {
                "alpha_gate"
            };
            return (regime, Some(reason.to_string()));
        }

        (RegimeState::Normal, None)
    }

    fn advance(&mut self, target: RegimeState, now_ns: u64, immediate: bool) -> RegimeState {
        if immediate && matches!(target, RegimeState::Chaos) {
            self.current = RegimeState::Chaos;
            self.pending = None;
            self.pending_since = now_ns;
            return self.current;
        }

        if target == self.current {
            self.pending = None;
            self.pending_since = now_ns;
            return self.current;
        }

        if self.params.hysteresis_ns == 0 {
            self.current = target;
            self.pending = None;
            self.pending_since = now_ns;
            return self.current;
        }

        if self.should_switch(now_ns) && self.pending == Some(target) {
            self.current = target;
            self.pending = None;
            self.pending_since = now_ns;
            return self.current;
        }

        if self.pending != Some(target) || self.pending_since == 0 {
            self.pending_since = now_ns;
        }
        self.pending = Some(target);
        self.current
    }

    fn should_switch(&self, now_ns: u64) -> bool {
        self.params.hysteresis_ns == 0
            || self.pending_since == 0
            || now_ns.saturating_sub(self.pending_since) >= self.params.hysteresis_ns
    }
}

/// Advisory returned to the Python layer / LiveRiskEngine integration.
#[derive(Debug, Clone)]
pub struct RiskDecision {
    pub regime: RegimeState,
    pub state: RiskState,
    pub widen_factor: f64,
    pub reduce_levels: u32,
    pub hedge_qty: f64,
    pub trend_bias: Option<TrendBias>,
    pub reason: Option<String>,
}

/// Rolling-risk helper evaluating regimes, volatility shocks, and soft inventory limits.
#[derive(Debug, Clone)]
pub struct RiskAdvisor {
    mode: RiskMode,
    vol_shock_sigma_mult: f64,
    inventory_soft_limit: f64,
    hedge_cooldown_ns: u64,
    hedge_min_qty: f64,
    last_hedge_ts: u64,
    regime: RegimeMachine,
}

impl RiskAdvisor {
    #[must_use]
    pub fn new(
        vol_shock_sigma_mult: f64,
        inventory_soft_limit: f64,
        hedge_cooldown_ms: f64,
        hedge_min_qty: f64,
        regime_params: RegimeParams,
        mode: RiskMode,
    ) -> Self {
        let cooldown_ns = (hedge_cooldown_ms.max(0.0) * 1_000_000.0).round() as u64;
        Self {
            mode,
            vol_shock_sigma_mult: vol_shock_sigma_mult.max(1.0),
            inventory_soft_limit: inventory_soft_limit.abs(),
            hedge_cooldown_ns: cooldown_ns,
            hedge_min_qty: hedge_min_qty.abs(),
            last_hedge_ts: 0,
            regime: RegimeMachine::new(regime_params),
        }
    }

    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn advise(
        &mut self,
        sigma_rel: f64,
        base_sigma: f64,
        inventory_qty: f64,
        alpha_bps: f64,
        delta_ratio: f64,
        mo_imbalance: f64,
        now_ns: u64,
    ) -> RiskDecision {
        let hedge_qty = self.maybe_hedge(inventory_qty, now_ns);
        if matches!(self.mode, RiskMode::NormalOnly) {
            return RiskDecision {
                regime: RegimeState::Normal,
                state: RiskState::Normal,
                widen_factor: 1.0,
                reduce_levels: 0,
                hedge_qty,
                trend_bias: None,
                reason: None,
            };
        }

        let base = base_sigma.max(1e-9);
        let sigma_ratio = (sigma_rel / base).abs();
        let (mut regime, mut trend_bias, mut reason) = self.regime.update(
            alpha_bps,
            delta_ratio,
            mo_imbalance,
            sigma_ratio,
            now_ns,
            self.vol_shock_sigma_mult,
        );

        let mut state = RiskState::Normal;
        let mut widen_factor = 1.0;
        let mut reduce_levels = 0;

        match regime {
            RegimeState::TrendUp | RegimeState::TrendDown => {
                state = RiskState::Widen;
                widen_factor = self.regime.params.trend_widen_mult;
                reduce_levels = self.regime.params.trend_reduce_levels;
            }
            RegimeState::Chaos => {
                state = if self.regime.params.pause_on_chaos {
                    RiskState::Pause
                } else {
                    RiskState::Widen
                };
                widen_factor = self.regime.params.chaos_widen_mult;
                reduce_levels = self.regime.params.chaos_reduce_levels;
            }
            RegimeState::Normal => {}
        }

        if sigma_ratio >= self.vol_shock_sigma_mult {
            // Explicitly mark chaos when vol explodes.
            regime = RegimeState::Chaos;
            trend_bias = None;
            state = RiskState::Pause;
            widen_factor = widen_factor.max(self.regime.params.chaos_widen_mult.max(2.0));
            reduce_levels = reduce_levels.max(self.regime.params.chaos_reduce_levels.max(2));
            reason = Some("vol_shock".to_string());
        } else if sigma_ratio >= self.vol_shock_sigma_mult * 0.7 {
            state = RiskState::Widen;
            widen_factor = widen_factor.max(1.5);
            reduce_levels = reduce_levels.max(1);
            reason.get_or_insert_with(|| "vol_spike".to_string());
        }

        RiskDecision {
            regime,
            state,
            widen_factor,
            reduce_levels,
            hedge_qty,
            trend_bias,
            reason,
        }
    }

    fn maybe_hedge(&mut self, qty: f64, now_ns: u64) -> f64 {
        if self.inventory_soft_limit <= 0.0 || qty.abs() < self.inventory_soft_limit {
            return 0.0;
        }
        if now_ns.saturating_sub(self.last_hedge_ts) < self.hedge_cooldown_ns {
            return 0.0;
        }
        self.last_hedge_ts = now_ns;
        if qty > 0.0 {
            self.hedge_min_qty
        } else {
            -self.hedge_min_qty
        }
    }
}
