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

//! Fill probability helpers shared by Aurora strategy bindings.

use std::f64::consts::SQRT_2;

use nautilus_model::enums::OrderSide;
use statrs::function::erf::erf;

/// Rolling queue statistics derived from order book deltas.
#[derive(Debug, Clone, Copy)]
pub struct QueueStats {
    lambda_mo: f64,
    lambda_cancel: f64,
    mean_mo: f64,
    var_mo: f64,
    touch_rate: f64,
}

impl Default for QueueStats {
    fn default() -> Self {
        Self::new(0.0, 0.0, 0.0, 0.0, 0.0)
    }
}

impl QueueStats {
    /// Create a new [`QueueStats`] sample with explicit seeds.
    #[must_use]
    pub fn new(
        lambda_mo: f64,
        lambda_cancel: f64,
        mean_mo: f64,
        var_mo: f64,
        touch_rate: f64,
    ) -> Self {
        Self {
            lambda_mo,
            lambda_cancel,
            mean_mo,
            var_mo,
            touch_rate,
        }
    }

    #[must_use]
    pub fn lambda_mo(&self) -> f64 {
        self.lambda_mo
    }

    #[must_use]
    pub fn lambda_cancel(&self) -> f64 {
        self.lambda_cancel
    }

    #[must_use]
    pub fn mean_mo(&self) -> f64 {
        self.mean_mo
    }

    #[must_use]
    pub fn var_mo(&self) -> f64 {
        self.var_mo
    }

    #[must_use]
    pub fn touch_rate(&self) -> f64 {
        self.touch_rate
    }

    pub fn set_lambda_mo(&mut self, value: f64) {
        self.lambda_mo = value;
    }

    pub fn set_lambda_cancel(&mut self, value: f64) {
        self.lambda_cancel = value;
    }

    pub fn set_mean_mo(&mut self, value: f64) {
        self.mean_mo = value;
    }

    pub fn set_var_mo(&mut self, value: f64) {
        self.var_mo = value;
    }

    pub fn set_touch_rate(&mut self, value: f64) {
        self.touch_rate = value;
    }

    /// EMA update from the latest queue observations.
    pub fn update(&mut self, mo_rate: f64, cxl_rate: f64, mean_mo: f64, var_mo: f64, decay: f64) {
        let decay = clamp_decay(decay);
        let inv = 1.0 - decay;
        self.lambda_mo = decay.mul_add(self.lambda_mo, inv * mo_rate);
        self.lambda_cancel = decay.mul_add(self.lambda_cancel, inv * cxl_rate);
        self.mean_mo = decay.mul_add(self.mean_mo, inv * mean_mo);
        self.var_mo = decay.mul_add(self.var_mo, inv * var_mo.max(1e-9));
    }

    /// EMA update incorporating the latest touch observation.
    pub fn update_touch(&mut self, hit: bool, dt_s: f64, decay: f64) {
        let decay = clamp_decay(decay);
        let rate_sample = if hit { 1.0 / dt_s.max(1e-6) } else { 0.0 };
        self.touch_rate = decay.mul_add(self.touch_rate, (1.0 - decay) * rate_sample);
    }
}

/// Two stage fill approximation used by Aurora queue computations.
#[derive(Debug, Clone)]
pub struct FillModel {
    min_p: f64,
    use_empirical_touch: bool,
    empirical_threshold: f64,
}

impl FillModel {
    /// Construct a new fill model.
    #[must_use]
    pub fn new(min_p: f64, tick_size: f64, use_empirical_touch: bool) -> Self {
        Self {
            min_p,
            use_empirical_touch,
            empirical_threshold: 1.5 * tick_size.max(1e-9),
        }
    }

    /// Probability of touching a quote within the time horizon.
    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn p_touch(
        &self,
        side: OrderSide,
        distance: f64,
        mu: f64,
        sigma_px: f64,
        horizon_s: f64,
        stats: Option<&QueueStats>,
    ) -> f64 {
        if horizon_s <= 0.0 {
            return 0.0;
        }

        if self.use_empirical_touch {
            if let Some(stats) = stats {
                if distance <= self.empirical_threshold && stats.touch_rate > 0.0 {
                    let prob = 1.0 - f64::exp(-stats.touch_rate * horizon_s);
                    return prob.clamp(0.0, 1.0);
                }
            }
        }

        if sigma_px <= 0.0 {
            return 0.0;
        }

        let signed = match side {
            OrderSide::Buy => -distance,
            OrderSide::Sell => distance,
            OrderSide::NoOrderSide => distance,
        };
        let drift = mu * horizon_s;
        let denom = sigma_px * horizon_s.sqrt();
        let z = (signed - drift) / denom;
        norm_cdf(z)
    }

    /// Probability that the resting queue is depleted.
    #[must_use]
    pub fn p_queue(&self, queue_ahead: f64, stats: &QueueStats, horizon_s: f64) -> f64 {
        if horizon_s <= 0.0 {
            return 0.0;
        }
        let lam = stats.lambda_mo + stats.lambda_cancel;
        if lam <= 0.0 {
            return 0.0;
        }
        let mean = lam * horizon_s * stats.mean_mo.max(1e-6);
        let var = lam * horizon_s * stats.var_mo.max(1e-6);
        let std = var.sqrt();
        if std <= 0.0 {
            return 0.0;
        }
        let z = (mean - queue_ahead.max(0.0)) / std;
        norm_cdf(z)
    }

    /// Combined fill probability.
    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn p_fill(
        &self,
        side: OrderSide,
        distance: f64,
        mu: f64,
        sigma_px: f64,
        horizon_s: f64,
        queue_ahead: f64,
        stats: &QueueStats,
    ) -> f64 {
        let p_touch = self.p_touch(side, distance, mu, sigma_px, horizon_s, Some(stats));
        if p_touch <= 0.0 {
            return 0.0;
        }
        let p_queue = self.p_queue(queue_ahead, stats, horizon_s);
        (p_touch * p_queue).clamp(self.min_p, 1.0)
    }
}

fn norm_cdf(z: f64) -> f64 {
    0.5 * (1.0 + erf(z / SQRT_2))
}

fn clamp_decay(decay: f64) -> f64 {
    decay.clamp(0.0, 0.999_999)
}
