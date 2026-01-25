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

//! Alpha model interfaces and implementations.

use anyhow::Result;

pub mod engine;
mod features;
mod metrics;
pub mod models;
pub mod training;

pub use engine::AlphaEngine;
pub use engine::{PredictPolicyConfig, SamplePolicyConfig, TriggerLogic};
pub use features::all_feature_names;
pub use metrics::{AlphaMetrics, OnlineCorr, VersionedAlphaMetrics};
pub use models::{
    ArcSwapModelHandle, InMemoryModelRegistry, LinearAlpha, ModelEntry, ModelHandle, ModelMetadata,
    ModelRegistry, OnnxPredictor, OnnxSession, Predictor, RlsAlpha, RlsParams, StaticPredictor,
    SwappableModel,
};
pub use training::{
    Labeler, LabeledSample, NoopTrainer, RlsTrainer, Sample, Trainer, UpdateDecision, UpdatePolicy,
    UpdatePolicyConfig, UpdateReason,
};

/// Generic alpha model interface.
pub trait AlphaModel: Send + Sync {
    /// Predict alpha in basis points given a feature vector.
    fn predict(&self, x: &[f64]) -> Result<f64>;
    /// Online update with a labeled alpha (bps).
    fn update(&mut self, x: &[f64], y_bps: f64) -> Result<()>;
    /// Expected feature dimension.
    fn dimension(&self) -> usize;
    /// Current weights (bps per feature).
    fn weights(&self) -> &[f64];
}
