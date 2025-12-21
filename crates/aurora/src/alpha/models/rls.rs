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
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

use anyhow::{Result, bail};
use nautilus_core::correctness::{
    check_in_range_inclusive_f64, check_in_range_inclusive_usize, check_predicate_true,
};

use crate::alpha::AlphaModel;

const MIN_DENOM: f64 = 1e-12;
const MIN_DIAGONAL: f64 = 1e-12;

/// Tunable parameters for the RLS model.
#[derive(Debug, Clone, Copy)]
pub struct RlsParams {
    pub forgetting: f64,
    pub ridge: f64,
    pub a_max_bps: f64,
}

impl Default for RlsParams {
    fn default() -> Self {
        Self {
            forgetting: 0.995,
            ridge: 1.0,
            a_max_bps: 3.0,
        }
    }
}

/// Simple RLS implementation for small feature dimensions.
#[derive(Debug, Clone)]
pub struct RlsAlpha {
    weights: Vec<f64>,
    p: Vec<f64>,
    params: RlsParams,
    scratch_px: Vec<f64>,
    scratch_xp: Vec<f64>,
}

impl RlsAlpha {
    /// Construct a new model with a given feature dimension.
    pub fn new(dimension: usize, params: RlsParams) -> Result<Self> {
        check_in_range_inclusive_usize(dimension, 1, usize::MAX, "dimension")?;
        check_predicate_true(
            params.ridge.is_finite() && params.ridge > 0.0,
            "RLS ridge must be > 0",
        )?;
        check_predicate_true(
            params.a_max_bps.is_finite() && params.a_max_bps > 0.0,
            "RLS a_max_bps must be > 0",
        )?;
        check_in_range_inclusive_f64(params.forgetting, 0.0, 1.0, "forgetting")?;

        let mut p = vec![0.0; dimension * dimension];
        for i in 0..dimension {
            p[idx(i, i, dimension)] = params.ridge;
        }
        Ok(Self {
            weights: vec![0.0; dimension],
            p,
            params,
            scratch_px: vec![0.0; dimension],
            scratch_xp: vec![0.0; dimension],
        })
    }
}

impl AlphaModel for RlsAlpha {
    fn predict(&self, x: &[f64]) -> Result<f64> {
        let dim = self.dimension();
        if x.len() != dim {
            bail!(
                "feature dimension mismatch: expected {dim}, got {}",
                x.len()
            );
        }
        let dot: f64 = self
            .weights
            .iter()
            .zip(x.iter())
            .map(|(w, xi)| w * xi)
            .sum();
        Ok(dot.clamp(-self.params.a_max_bps, self.params.a_max_bps))
    }

    fn update(&mut self, x: &[f64], y_bps: f64) -> Result<()> {
        let dim = self.dimension();
        if x.len() != dim {
            bail!(
                "feature dimension mismatch: expected {dim}, got {}",
                x.len()
            );
        }
        let forget = self.params.forgetting;
        check_predicate_true(forget > 0.0, "RLS forgetting must be > 0")?;

        self.scratch_px.fill(0.0);
        for i in 0..dim {
            self.scratch_px[i] = row_dot(&self.p, i, x, dim);
        }
        let mut denom = forget + dot(&self.scratch_px, x);
        if !denom.is_finite() {
            bail!("RLS denominator was not finite");
        }
        if denom <= 0.0 {
            denom = MIN_DENOM;
        }

        let k: Vec<f64> = self.scratch_px.iter().map(|v| v / denom).collect();
        let y_hat = dot(&self.weights, x);
        let error = y_bps - y_hat;

        for i in 0..dim {
            self.weights[i] += k[i] * error;
        }

        // Compute x^T P
        self.scratch_xp.fill(0.0);
        for j in 0..dim {
            let mut acc = 0.0;
            for (l, &xl) in x.iter().enumerate() {
                acc += xl * self.p[idx(l, j, dim)];
            }
            self.scratch_xp[j] = acc;
        }

        // P = (P - k * x^T * P) / forget
        for i in 0..dim {
            for j in 0..dim {
                let new_val = (self.p[idx(i, j, dim)] - k[i] * self.scratch_xp[j]) / forget;
                self.p[idx(i, j, dim)] = new_val;
            }
        }
        self.symmetrize();
        Ok(())
    }

    fn dimension(&self) -> usize {
        self.weights.len()
    }

    fn weights(&self) -> &[f64] {
        &self.weights
    }
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

fn row_dot(p: &[f64], row: usize, x: &[f64], dim: usize) -> f64 {
    let mut acc = 0.0;
    let start = row * dim;
    for (offset, &xi) in x.iter().enumerate() {
        acc += p[start + offset] * xi;
    }
    acc
}

fn idx(i: usize, j: usize, dim: usize) -> usize {
    i * dim + j
}

impl RlsAlpha {
    fn symmetrize(&mut self) {
        let dim = self.dimension();
        for i in 0..dim {
            let diag = &mut self.p[idx(i, i, dim)];
            if !diag.is_finite() || *diag <= 0.0 {
                *diag = MIN_DIAGONAL;
            }
            for j in 0..i {
                let a = self.p[idx(i, j, dim)];
                let b = self.p[idx(j, i, dim)];
                let v = 0.5 * (a + b);
                self.p[idx(i, j, dim)] = v;
                self.p[idx(j, i, dim)] = v;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{RlsAlpha, RlsParams};
    use crate::alpha::AlphaModel;

    #[test]
    fn rls_new_rejects_bad_params() {
        assert!(RlsAlpha::new(0, RlsParams::default()).is_err());
        assert!(
            RlsAlpha::new(
                2,
                RlsParams {
                    ridge: 0.0,
                    ..Default::default()
                }
            )
            .is_err()
        );
        assert!(
            RlsAlpha::new(
                2,
                RlsParams {
                    a_max_bps: -1.0,
                    ..Default::default()
                }
            )
            .is_err()
        );
        assert!(
            RlsAlpha::new(
                2,
                RlsParams {
                    forgetting: 1.5,
                    ..Default::default()
                }
            )
            .is_err()
        );
    }

    #[test]
    fn rls_dimension_mismatch_errors() {
        let mut model = RlsAlpha::new(2, RlsParams::default()).unwrap();
        assert!(model.predict(&[1.0]).is_err());
        assert!(model.update(&[1.0], 0.0).is_err());
    }

    #[test]
    fn rls_clips_prediction() {
        let mut model = RlsAlpha::new(
            1,
            RlsParams {
                a_max_bps: 1.0,
                ..Default::default()
            },
        )
        .unwrap();
        // Drive weight upward with a large target then ensure prediction is clipped.
        model.update(&[10.0], 100.0).unwrap();
        let out = model.predict(&[10.0]).unwrap();
        assert_eq!(out, 1.0);
    }

    #[test]
    fn rls_learns_simple_signal() {
        let mut model = RlsAlpha::new(
            1,
            RlsParams {
                forgetting: 0.9,
                ridge: 1.0,
                a_max_bps: 10.0,
            },
        )
        .unwrap();
        for _ in 0..50 {
            model.update(&[1.0], 5.0).unwrap();
        }
        let w = model.weights()[0];
        assert!((w - 5.0).abs() < 0.5);
        let pred = model.predict(&[1.0]).unwrap();
        assert!((pred - 5.0).abs() < 0.5);
    }
}
