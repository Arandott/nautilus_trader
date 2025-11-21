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

//! Lightweight risk advisories (volatility modes, inventory hedges) used by Aurora.

/// Coarse risk states mirrored in Python strategy logic.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskState {
    Normal,
    Widen,
    Pause,
}

/// Advisory returned to the Python layer / LiveRiskEngine integration.
#[derive(Debug, Clone)]
pub struct RiskDecision {
    pub state: RiskState,
    pub widen_factor: f64,
    pub reduce_levels: u32,
    pub hedge_qty: f64,
    pub reason: Option<String>,
}

/// Rolling-risk helper evaluating volatility shocks and soft inventory limits.
#[derive(Debug, Clone)]
pub struct RiskAdvisor {
    vol_shock_sigma_mult: f64,
    inventory_soft_limit: f64,
    hedge_cooldown_ns: u64,
    hedge_min_qty: f64,
    last_hedge_ts: u64,
}

impl RiskAdvisor {
    #[must_use]
    pub fn new(
        vol_shock_sigma_mult: f64,
        inventory_soft_limit: f64,
        hedge_cooldown_ms: f64,
        hedge_min_qty: f64,
    ) -> Self {
        let cooldown_ns = (hedge_cooldown_ms.max(0.0) * 1_000_000.0).round() as u64;
        Self {
            vol_shock_sigma_mult: vol_shock_sigma_mult.max(1.0),
            inventory_soft_limit: inventory_soft_limit.abs(),
            hedge_cooldown_ns: cooldown_ns,
            hedge_min_qty: hedge_min_qty.abs(),
            last_hedge_ts: 0,
        }
    }

    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn advise(
        &mut self,
        sigma_rel: f64,
        base_sigma: f64,
        inventory_qty: f64,
        now_ns: u64,
    ) -> RiskDecision {
        let base = base_sigma.max(1e-9);
        let sigma_ratio = (sigma_rel / base).abs();
        let mut state = RiskState::Normal;
        let mut widen_factor = 1.0;
        let mut reduce_levels = 0;
        let mut reason = None;

        if sigma_ratio >= self.vol_shock_sigma_mult {
            state = RiskState::Pause;
            widen_factor = 2.0;
            reduce_levels = 2;
            reason = Some("vol_shock".to_string());
        } else if sigma_ratio >= self.vol_shock_sigma_mult * 0.7 {
            state = RiskState::Widen;
            widen_factor = 1.5;
            reduce_levels = 1;
            reason = Some("vol_spike".to_string());
        }

        let hedge_qty = self.maybe_hedge(inventory_qty, now_ns);

        RiskDecision {
            state,
            widen_factor,
            reduce_levels,
            hedge_qty,
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
