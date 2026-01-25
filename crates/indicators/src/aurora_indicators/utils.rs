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

use std::collections::VecDeque;

pub const DEFAULT_EPS: f64 = 1e-12;

#[inline]
pub fn sanitize_f64(value: f64) -> f64 {
    if value.is_finite() { value } else { 0.0 }
}

#[inline]
pub fn safe_div(numerator: f64, denominator: f64, eps: f64) -> f64 {
    if !numerator.is_finite() || !denominator.is_finite() || denominator.abs() <= eps {
        0.0
    } else {
        numerator / denominator
    }
}

#[inline]
pub fn safe_sqrt(value: f64) -> f64 {
    if value.is_finite() && value > 0.0 { value.sqrt() } else { 0.0 }
}

#[derive(Debug)]
pub struct RollingWindow {
    window: usize,
    values: VecDeque<f64>,
    sum: f64,
    sumsq: f64,
    sumcube: f64,
    sumquad: f64,
}

impl RollingWindow {
    #[must_use]
    pub fn new(window: usize) -> Self {
        Self {
            window: window.max(1),
            values: VecDeque::with_capacity(window.max(1)),
            sum: 0.0,
            sumsq: 0.0,
            sumcube: 0.0,
            sumquad: 0.0,
        }
    }

    pub fn push(&mut self, value: f64) {
        let value = sanitize_f64(value);
        self.values.push_back(value);
        self.sum += value;
        self.sumsq += value * value;
        self.sumcube += value * value * value;
        self.sumquad += value * value * value * value;

        if self.values.len() > self.window {
            if let Some(old) = self.values.pop_front() {
                self.sum -= old;
                self.sumsq -= old * old;
                self.sumcube -= old * old * old;
                self.sumquad -= old * old * old * old;
            }
        }
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.values.len()
    }

    #[must_use]
    pub fn is_full(&self) -> bool {
        self.values.len() >= self.window
    }

    #[must_use]
    pub fn sum(&self) -> f64 {
        self.sum
    }

    #[must_use]
    pub fn mean(&self) -> f64 {
        safe_div(self.sum, self.len() as f64, DEFAULT_EPS)
    }

    #[must_use]
    pub fn var(&self) -> f64 {
        let n = self.len() as f64;
        if n <= 0.0 {
            return 0.0;
        }
        let mean = safe_div(self.sum, n, DEFAULT_EPS);
        let variance = safe_div(self.sumsq, n, DEFAULT_EPS) - mean * mean;
        if variance.is_finite() && variance > 0.0 { variance } else { 0.0 }
    }

    #[must_use]
    pub fn std(&self) -> f64 {
        safe_sqrt(self.var())
    }

    #[must_use]
    pub fn skew(&self) -> f64 {
        let n = self.len() as f64;
        if n <= 0.0 {
            return 0.0;
        }
        let mean = safe_div(self.sum, n, DEFAULT_EPS);
        let m2 = safe_div(self.sumsq, n, DEFAULT_EPS) - mean * mean;
        if m2 <= 0.0 {
            return 0.0;
        }
        let m3 = safe_div(self.sumcube, n, DEFAULT_EPS)
            - 3.0 * mean * safe_div(self.sumsq, n, DEFAULT_EPS)
            + 2.0 * mean * mean * mean;
        safe_div(m3, m2.powf(1.5), DEFAULT_EPS)
    }

    #[must_use]
    pub fn kurtosis(&self) -> f64 {
        let n = self.len() as f64;
        if n <= 0.0 {
            return 0.0;
        }
        let mean = safe_div(self.sum, n, DEFAULT_EPS);
        let m2 = safe_div(self.sumsq, n, DEFAULT_EPS) - mean * mean;
        if m2 <= 0.0 {
            return 0.0;
        }
        let m4 = safe_div(self.sumquad, n, DEFAULT_EPS)
            - 4.0 * mean * safe_div(self.sumcube, n, DEFAULT_EPS)
            + 6.0 * mean * mean * safe_div(self.sumsq, n, DEFAULT_EPS)
            - 3.0 * mean * mean * mean * mean;
        safe_div(m4, m2 * m2, DEFAULT_EPS)
    }

    #[must_use]
    pub fn min(&self) -> f64 {
        self.values
            .iter()
            .copied()
            .fold(f64::INFINITY, |acc, val| acc.min(val))
            .is_finite()
            .then_some(
                self.values
                    .iter()
                    .copied()
                    .fold(f64::INFINITY, |acc, val| acc.min(val)),
            )
            .unwrap_or(0.0)
    }

    #[must_use]
    pub fn max(&self) -> f64 {
        self.values
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, |acc, val| acc.max(val))
            .is_finite()
            .then_some(
                self.values
                    .iter()
                    .copied()
                    .fold(f64::NEG_INFINITY, |acc, val| acc.max(val)),
            )
            .unwrap_or(0.0)
    }

    #[must_use]
    pub fn quantile(&self, q: f64) -> f64 {
        if self.values.is_empty() {
            return 0.0;
        }
        let mut vals: Vec<f64> = self.values.iter().copied().collect();
        vals.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let q = q.clamp(0.0, 1.0);
        let idx = ((vals.len() as f64 - 1.0) * q).round() as usize;
        vals.get(idx).copied().unwrap_or(0.0)
    }

    #[must_use]
    pub fn median(&self) -> f64 {
        self.quantile(0.5)
    }

    #[must_use]
    pub fn values(&self) -> &VecDeque<f64> {
        &self.values
    }
}

#[derive(Debug)]
pub struct RollingCorrelation {
    window: usize,
    values: VecDeque<(f64, f64)>,
    sum_x: f64,
    sum_y: f64,
    sum_x2: f64,
    sum_y2: f64,
    sum_xy: f64,
}

impl RollingCorrelation {
    #[must_use]
    pub fn new(window: usize) -> Self {
        Self {
            window: window.max(1),
            values: VecDeque::with_capacity(window.max(1)),
            sum_x: 0.0,
            sum_y: 0.0,
            sum_x2: 0.0,
            sum_y2: 0.0,
            sum_xy: 0.0,
        }
    }

    pub fn push(&mut self, x: f64, y: f64) {
        let x = sanitize_f64(x);
        let y = sanitize_f64(y);
        self.values.push_back((x, y));
        self.sum_x += x;
        self.sum_y += y;
        self.sum_x2 += x * x;
        self.sum_y2 += y * y;
        self.sum_xy += x * y;

        if self.values.len() > self.window {
            if let Some((old_x, old_y)) = self.values.pop_front() {
                self.sum_x -= old_x;
                self.sum_y -= old_y;
                self.sum_x2 -= old_x * old_x;
                self.sum_y2 -= old_y * old_y;
                self.sum_xy -= old_x * old_y;
            }
        }
    }

    #[must_use]
    pub fn is_full(&self) -> bool {
        self.values.len() >= self.window
    }

    #[must_use]
    pub fn corr(&self) -> f64 {
        let n = self.values.len() as f64;
        if n <= 1.0 {
            return 0.0;
        }
        let num = n * self.sum_xy - self.sum_x * self.sum_y;
        let den_x = n * self.sum_x2 - self.sum_x * self.sum_x;
        let den_y = n * self.sum_y2 - self.sum_y * self.sum_y;
        let denom = safe_sqrt(den_x * den_y);
        safe_div(num, denom, DEFAULT_EPS)
    }
}

#[derive(Debug)]
pub struct RollingLWMA {
    window: usize,
    values: VecDeque<f64>,
    sum: f64,
    weighted_sum: f64,
}

impl RollingLWMA {
    #[must_use]
    pub fn new(window: usize) -> Self {
        Self {
            window: window.max(1),
            values: VecDeque::with_capacity(window.max(1)),
            sum: 0.0,
            weighted_sum: 0.0,
        }
    }

    pub fn push(&mut self, value: f64) {
        let value = sanitize_f64(value);
        self.values.push_back(value);
        self.sum += value;
        let len = self.values.len() as f64;
        self.weighted_sum += value * len;

        if self.values.len() > self.window {
            let old_sum = self.sum;
            if let Some(old) = self.values.pop_front() {
                self.sum -= old;
                self.weighted_sum -= old_sum;
            }
        }
    }

    #[must_use]
    pub fn is_full(&self) -> bool {
        self.values.len() >= self.window
    }

    #[must_use]
    pub fn value(&self) -> f64 {
        let n = self.values.len() as f64;
        if n <= 0.0 {
            return 0.0;
        }
        let weight_total = n * (n + 1.0) * 0.5;
        safe_div(self.weighted_sum, weight_total, DEFAULT_EPS)
    }
}

#[derive(Debug)]
pub struct LagBuffer {
    lag: usize,
    values: VecDeque<f64>,
}

impl LagBuffer {
    #[must_use]
    pub fn new(lag: usize) -> Self {
        Self {
            lag: lag.max(1),
            values: VecDeque::with_capacity(lag.max(1) + 1),
        }
    }

    pub fn push(&mut self, value: f64) -> Option<f64> {
        let value = sanitize_f64(value);
        self.values.push_back(value);
        if self.values.len() > self.lag {
            self.values.pop_front()
        } else {
            None
        }
    }

    #[must_use]
    pub fn is_full(&self) -> bool {
        self.values.len() > self.lag
    }
}

#[inline]
pub fn diff_ratio(current: f64, previous: f64) -> f64 {
    safe_div(current - previous, previous, DEFAULT_EPS)
}

#[inline]
pub fn sign(value: f64) -> f64 {
    if value > 0.0 {
        1.0
    } else if value < 0.0 {
        -1.0
    } else {
        0.0
    }
}

#[inline]
pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let sum: f64 = values.iter().copied().sum();
    safe_div(sum, values.len() as f64, DEFAULT_EPS)
}

#[inline]
pub fn std(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mu = mean(values);
    let sum = values
        .iter()
        .map(|v| {
            let diff = v - mu;
            diff * diff
        })
        .sum::<f64>();
    let var = safe_div(sum, values.len() as f64, DEFAULT_EPS);
    safe_sqrt(var)
}

#[inline]
pub fn ols_slope(x: &[f64], y: &[f64]) -> f64 {
    if x.len() != y.len() || x.is_empty() {
        return 0.0;
    }
    let n = x.len() as f64;
    let sum_x: f64 = x.iter().sum();
    let sum_y: f64 = y.iter().sum();
    let sum_x2: f64 = x.iter().map(|v| v * v).sum();
    let sum_xy: f64 = x.iter().zip(y.iter()).map(|(a, b)| a * b).sum();
    let denom = n * sum_x2 - sum_x * sum_x;
    safe_div(n * sum_xy - sum_x * sum_y, denom, DEFAULT_EPS)
}

#[inline]
pub fn ols_intercept(x: &[f64], y: &[f64]) -> f64 {
    if x.len() != y.len() || x.is_empty() {
        return 0.0;
    }
    let slope = ols_slope(x, y);
    let mean_x = mean(x);
    let mean_y = mean(y);
    mean_y - slope * mean_x
}

#[inline]
pub fn ols_r2(x: &[f64], y: &[f64]) -> f64 {
    if x.len() != y.len() || x.len() < 2 {
        return 0.0;
    }
    let slope = ols_slope(x, y);
    let intercept = ols_intercept(x, y);
    let mean_y = mean(y);
    let mut ss_tot = 0.0;
    let mut ss_res = 0.0;
    for (xi, yi) in x.iter().zip(y.iter()) {
        let pred = intercept + slope * xi;
        let diff = yi - pred;
        let diff_mean = yi - mean_y;
        ss_res += diff * diff;
        ss_tot += diff_mean * diff_mean;
    }
    if ss_tot <= DEFAULT_EPS {
        0.0
    } else {
        1.0 - safe_div(ss_res, ss_tot, DEFAULT_EPS)
    }
}
