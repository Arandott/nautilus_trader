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

//! Linear alpha model for offline-trained weights (predict-only by default).

use anyhow::{Result, bail};

use crate::alpha::AlphaModel;

/// Linear model with optional output clamp.
#[derive(Debug, Clone)]
pub struct LinearAlpha {
    weights: Vec<f64>,
    bias: f64,
    a_max_bps: Option<f64>,
}

impl LinearAlpha {
    /// Build a linear alpha model from offline-trained weights.
    pub fn new(weights: Vec<f64>, bias: f64, a_max_bps: Option<f64>) -> Result<Self> {
        if weights.is_empty() {
            bail!("linear alpha weights must be non-empty");
        }
        if !bias.is_finite() {
            bail!("linear alpha bias must be finite");
        }
        for (idx, w) in weights.iter().enumerate() {
            if !w.is_finite() {
                bail!("linear alpha weight at index {idx} was not finite");
            }
        }
        if let Some(max) = a_max_bps {
            if !max.is_finite() || max <= 0.0 {
                bail!("linear alpha a_max_bps must be > 0 and finite");
            }
        }
        Ok(Self {
            weights,
            bias,
            a_max_bps,
        })
    }

    pub fn bias(&self) -> f64 {
        self.bias
    }

    pub fn a_max_bps(&self) -> Option<f64> {
        self.a_max_bps
    }
}

impl AlphaModel for LinearAlpha {
    fn predict(&self, x: &[f64]) -> Result<f64> {
        let dim = self.dimension();
        if x.len() != dim {
            bail!("feature dimension mismatch: expected {dim}, got {}", x.len());
        }
        let mut out = self.bias;
        for (w, xi) in self.weights.iter().zip(x.iter()) {
            out += w * xi;
        }
        if let Some(max) = self.a_max_bps {
            return Ok(out.clamp(-max, max));
        }
        Ok(out)
    }

    fn update(&mut self, x: &[f64], _y_bps: f64) -> Result<()> {
        let dim = self.dimension();
        if x.len() != dim {
            bail!("feature dimension mismatch: expected {dim}, got {}", x.len());
        }
        Ok(())
    }

    fn dimension(&self) -> usize {
        self.weights.len()
    }

    fn weights(&self) -> &[f64] {
        &self.weights
    }
}
