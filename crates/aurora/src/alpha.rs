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

//! Lightweight Recursive Least Squares alpha model.

/// Generic alpha model interface.
pub trait AlphaModel {
    /// Predict alpha in basis points given a feature vector.
    fn predict(&self, x: &[f64]) -> f64;
    /// Online update with a labeled alpha (bps).
    fn update(&mut self, x: &[f64], y_bps: f64);
}

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
    p: Vec<Vec<f64>>,
    params: RlsParams,
}

impl RlsAlpha {
    /// Construct a new model with a given feature dimension.
    pub fn new(dimension: usize, params: RlsParams) -> Self {
        let dim = dimension.max(1);
        let mut p = vec![vec![0.0; dim]; dim];
        for i in 0..dim {
            p[i][i] = params.ridge;
        }
        Self {
            weights: vec![0.0; dim],
            p,
            params,
        }
    }

    /// Dimension of the feature vector expected.
    #[must_use]
    pub fn dimension(&self) -> usize {
        self.weights.len()
    }

    /// Predict alpha (bps), clipped to [-a_max, a_max].
    #[must_use]
    pub fn predict(&self, x: &[f64]) -> f64 {
        let dim = self.dimension();
        if x.len() != dim {
            return 0.0;
        }
        let dot: f64 = self.weights.iter().zip(x.iter()).map(|(w, xi)| w * xi).sum();
        dot.clamp(-self.params.a_max_bps, self.params.a_max_bps)
    }

    /// Update model state with a labeled sample.
    pub fn update(&mut self, x: &[f64], y_bps: f64) {
        let dim = self.dimension();
        if x.len() != dim {
            return;
        }

        let forget = self.params.forgetting.clamp(0.5, 1.0);
        let mut px = vec![0.0; dim];
        for i in 0..dim {
            px[i] = dot(&self.p[i], x);
        }
        let denom = forget + dot(&px, x);
        if denom <= 0.0 {
            return;
        }

        let k: Vec<f64> = px.iter().map(|v| v / denom).collect();
        let y_hat = dot(&self.weights, x);
        let error = y_bps - y_hat;

        for i in 0..dim {
            self.weights[i] += k[i] * error;
        }

        // Compute x^T P
        let mut xp = vec![0.0; dim];
        for j in 0..dim {
            for (l, &xl) in x.iter().enumerate() {
                xp[j] += xl * self.p[l][j];
            }
        }

        // P = (P - k * x^T * P) / forget
        for i in 0..dim {
            for j in 0..dim {
                self.p[i][j] = (self.p[i][j] - k[i] * xp[j]) / forget;
            }
        }
    }

    /// Access learned weights (bps per feature).
    #[must_use]
    pub fn weights(&self) -> &[f64] {
        &self.weights
    }
}

impl AlphaModel for RlsAlpha {
    fn predict(&self, x: &[f64]) -> f64 {
        RlsAlpha::predict(self, x)
    }

    fn update(&mut self, x: &[f64], y_bps: f64) {
        RlsAlpha::update(self, x, y_bps);
    }
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}
