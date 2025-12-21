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

//! Predictor and model handle abstractions for hot-swapping alpha models.

use std::sync::Arc;

use anyhow::Result;
use arc_swap::ArcSwap;

use crate::alpha::AlphaModel;

pub trait Predictor: Send + Sync + std::fmt::Debug {
    fn predict(&self, x: &[f64]) -> Result<f64>;
    fn dimension(&self) -> usize;
    fn version(&self) -> &str;
}

#[derive(Debug, Clone)]
pub struct StaticPredictor<M: AlphaModel> {
    model: M,
    version: Arc<str>,
}

impl<M: AlphaModel> StaticPredictor<M> {
    pub fn new(model: M, version: impl Into<Arc<str>>) -> Self {
        Self {
            model,
            version: version.into(),
        }
    }
}

impl<M: AlphaModel + std::fmt::Debug> Predictor for StaticPredictor<M> {
    fn predict(&self, x: &[f64]) -> Result<f64> {
        self.model.predict(x)
    }

    fn dimension(&self) -> usize {
        self.model.dimension()
    }

    fn version(&self) -> &str {
        &self.version
    }
}

pub trait ModelHandle: Send + Sync + std::fmt::Debug {
    fn predictor(&self) -> Arc<dyn Predictor>;
    fn swap(&self, new_model: Arc<dyn Predictor>);
}

#[derive(Debug)]
pub struct ArcSwapModelHandle {
    inner: ArcSwap<Arc<dyn Predictor>>,
}

impl ArcSwapModelHandle {
    pub fn new(model: Arc<dyn Predictor>) -> Self {
        Self {
            inner: ArcSwap::from_pointee(model),
        }
    }

    pub fn predictor(&self) -> Arc<dyn Predictor> {
        let current = self.inner.load_full();
        Arc::clone(current.as_ref())
    }

    pub fn swap(&self, new_model: Arc<dyn Predictor>) {
        self.inner.store(Arc::new(new_model));
    }
}

impl ModelHandle for ArcSwapModelHandle {
    fn predictor(&self) -> Arc<dyn Predictor> {
        self.predictor()
    }

    fn swap(&self, new_model: Arc<dyn Predictor>) {
        self.swap(new_model);
    }
}

#[derive(Debug, Clone)]
pub struct SwappableModel {
    handle: Arc<dyn ModelHandle>,
}

impl SwappableModel {
    pub fn new(handle: Arc<dyn ModelHandle>) -> Self {
        Self { handle }
    }

    pub fn handle(&self) -> Arc<dyn ModelHandle> {
        Arc::clone(&self.handle)
    }
}

impl AlphaModel for SwappableModel {
    fn predict(&self, x: &[f64]) -> Result<f64> {
        self.handle.predictor().predict(x)
    }

    fn update(&mut self, _x: &[f64], _y_bps: f64) -> Result<()> {
        Ok(())
    }

    fn dimension(&self) -> usize {
        self.handle.predictor().dimension()
    }

    fn weights(&self) -> &[f64] {
        &[]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result as AnyResult;
    use crate::alpha::AlphaModel;

    #[derive(Debug)]
    struct DummyPredictor {
        dim: usize,
        value: f64,
        version: &'static str,
    }

    impl Predictor for DummyPredictor {
        fn predict(&self, _x: &[f64]) -> AnyResult<f64> {
            Ok(self.value)
        }

        fn dimension(&self) -> usize {
            self.dim
        }

        fn version(&self) -> &str {
            self.version
        }
    }

    #[test]
    fn arc_swap_handle_swaps_predictor() {
        let p1: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            dim: 2,
            value: 1.0,
            version: "v1",
        });
        let p2: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            dim: 2,
            value: 2.0,
            version: "v2",
        });

        let handle = ArcSwapModelHandle::new(p1);
        assert_eq!(handle.predictor().version(), "v1");
        handle.swap(p2);
        assert_eq!(handle.predictor().version(), "v2");
    }

    #[test]
    fn swappable_model_uses_latest_predictor() {
        let p1: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            dim: 1,
            value: 1.0,
            version: "v1",
        });
        let p2: Arc<dyn Predictor> = Arc::new(DummyPredictor {
            dim: 1,
            value: -1.0,
            version: "v2",
        });
        let handle = Arc::new(ArcSwapModelHandle::new(p1));
        let model = SwappableModel::new(handle.clone());

        let pred1 = model.predict(&[0.0]).unwrap();
        assert!((pred1 - 1.0).abs() < 1e-9);

        handle.swap(p2);
        let pred2 = model.predict(&[0.0]).unwrap();
        assert!((pred2 + 1.0).abs() < 1e-9);
    }

    #[test]
    fn static_predictor_wraps_alpha_model() {
        #[derive(Debug, Clone)]
        struct ConstModel {
            dim: usize,
            value: f64,
        }

        impl AlphaModel for ConstModel {
            fn predict(&self, _x: &[f64]) -> AnyResult<f64> {
                Ok(self.value)
            }

            fn update(&mut self, _x: &[f64], _y_bps: f64) -> AnyResult<()> {
                Ok(())
            }

            fn dimension(&self) -> usize {
                self.dim
            }

            fn weights(&self) -> &[f64] {
                &[]
            }
        }

        let predictor = StaticPredictor::new(ConstModel { dim: 3, value: 0.5 }, "local");
        assert_eq!(predictor.dimension(), 3);
        assert_eq!(predictor.version(), "local");
        let pred = predictor.predict(&[0.0, 0.0, 0.0]).unwrap();
        assert!((pred - 0.5).abs() < 1e-9);
    }
}
