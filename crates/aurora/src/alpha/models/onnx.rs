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

//! ONNX predictor skeleton (runtime implementation is provided externally).

use std::sync::Arc;

use anyhow::{Result, bail};

use crate::alpha::Predictor;

pub trait OnnxSession: Send + Sync + std::fmt::Debug {
    fn run(&self, features: &[f64]) -> Result<f64>;
    fn dimension(&self) -> usize;
}

#[derive(Debug, Clone)]
pub struct OnnxPredictor {
    session: Arc<dyn OnnxSession>,
    version: Arc<str>,
}

impl OnnxPredictor {
    pub fn new(session: Arc<dyn OnnxSession>, version: impl Into<Arc<str>>) -> Self {
        Self {
            session,
            version: version.into(),
        }
    }
}

impl Predictor for OnnxPredictor {
    fn predict(&self, x: &[f64]) -> Result<f64> {
        if x.len() != self.session.dimension() {
            bail!(
                "feature dimension mismatch: expected {}, got {}",
                self.session.dimension(),
                x.len()
            );
        }
        self.session.run(x)
    }

    fn dimension(&self) -> usize {
        self.session.dimension()
    }

    fn version(&self) -> &str {
        &self.version
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result as AnyResult;

    #[derive(Debug)]
    struct DummySession {
        dim: usize,
        value: f64,
    }

    impl OnnxSession for DummySession {
        fn run(&self, _features: &[f64]) -> AnyResult<f64> {
            Ok(self.value)
        }

        fn dimension(&self) -> usize {
            self.dim
        }
    }

    #[test]
    fn onnx_predictor_runs_session() {
        let session = Arc::new(DummySession { dim: 2, value: 1.5 });
        let predictor = OnnxPredictor::new(session, "onnx-v1");
        let pred = predictor.predict(&[0.0, 0.0]).unwrap();
        assert!((pred - 1.5).abs() < 1e-9);
    }

    #[test]
    fn onnx_predictor_rejects_dimension_mismatch() {
        let session = Arc::new(DummySession { dim: 2, value: 1.0 });
        let predictor = OnnxPredictor::new(session, "onnx-v1");
        let err = predictor.predict(&[0.0]).unwrap_err();
        assert!(err.to_string().contains("feature dimension mismatch"));
    }
}
