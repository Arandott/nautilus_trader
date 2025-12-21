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

//! Trainer abstraction and update policy for alpha models.

use anyhow::Result;

use crate::alpha::AlphaModel;
use super::labeler::LabeledSample;

/// Lightweight update policy: controls when to train, with optional sampling/clipping.
#[derive(Debug, Clone)]
pub struct UpdatePolicy {
    pub min_update_interval_ns: i64,  // 0 disables time throttle
    pub count_stride: usize,          // 1 means every eligible label updates
    pub sample_rate: f64,             // 1.0 means no sampling
    pub label_clip_bps: Option<f64>,  // absolute clip; None to disable
    pub label_min_abs_bps: Option<f64>, // skip if abs(label) below threshold
    pub mid_required: bool,           // skip if mid<=0 when true
    // state
    pub last_update_ns: i64,
    pub since_last: usize,
    pub rng_state: u64,
}

#[derive(Debug, Clone, Copy)]
pub enum UpdateDecision {
    Apply { label_bps: f64, reason: UpdateReason },
    Skip(UpdateReason),
}

#[derive(Debug, Clone, Copy)]
pub enum UpdateReason {
    None,
    TimeThrottle,
    CountThrottle,
    SampledOut,
    LabelTooSmall,
    LabelClipped,
    MidInvalid,
}

#[derive(Debug, Clone)]
pub struct UpdatePolicyConfig {
    pub min_update_interval_ns: i64,
    pub count_stride: usize,
    pub sample_rate: f64,
    pub label_clip_bps: Option<f64>,
    pub label_min_abs_bps: Option<f64>,
    pub mid_required: bool,
}

impl Default for UpdatePolicyConfig {
    fn default() -> Self {
        Self {
            min_update_interval_ns: 0,
            count_stride: 1,
            sample_rate: 1.0,
            label_clip_bps: None,
            label_min_abs_bps: None,
            mid_required: true,
        }
    }
}

impl UpdatePolicy {
    pub fn from_config(config: UpdatePolicyConfig) -> Self {
        Self {
            min_update_interval_ns: config.min_update_interval_ns.max(0),
            count_stride: config.count_stride.max(1),
            sample_rate: config.sample_rate.clamp(0.0, 1.0),
            label_clip_bps: config.label_clip_bps,
            label_min_abs_bps: config.label_min_abs_bps,
            mid_required: config.mid_required,
            last_update_ns: 0,
            since_last: 0,
            rng_state: 0x9E37_79B9_7F4A_7C15,
        }
    }

    #[inline]
    pub fn should_update(&mut self, ts_ns: i64, label_bps: f64, mid: f64) -> UpdateDecision {
        if self.mid_required && mid <= 0.0 {
            return UpdateDecision::Skip(UpdateReason::MidInvalid);
        }

        if self.label_min_abs_bps.map_or(false, |thr| label_bps.abs() < thr) {
            return UpdateDecision::Skip(UpdateReason::LabelTooSmall);
        }

        if self.min_update_interval_ns > 0
            && self.last_update_ns > 0
            && ts_ns - self.last_update_ns < self.min_update_interval_ns
        {
            self.since_last += 1;
            return UpdateDecision::Skip(UpdateReason::TimeThrottle);
        }

        if self.count_stride > 1 && self.since_last + 1 < self.count_stride {
            self.since_last += 1;
            return UpdateDecision::Skip(UpdateReason::CountThrottle);
        }

        if self.sample_rate < 1.0 {
            // simple LCG to avoid external RNG deps; high bits for fraction.
            self.rng_state = self
                .rng_state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1);
            let frac =
                ((self.rng_state >> 11) as f64) * (1.0 / (1u64 << 53) as f64);
            if frac > self.sample_rate {
                self.since_last += 1;
                return UpdateDecision::Skip(UpdateReason::SampledOut);
            }
        }

        let mut out_label = label_bps;
        let mut reason = UpdateReason::None;
        if let Some(clip) = self.label_clip_bps {
            if label_bps.abs() > clip {
                out_label = label_bps.signum() * clip;
                reason = UpdateReason::LabelClipped;
            }
        }

        self.last_update_ns = ts_ns;
        self.since_last = 0;
        UpdateDecision::Apply {
            label_bps: out_label,
            reason,
        }
    }
}

pub trait Trainer<M: AlphaModel>: Send + Sync + std::fmt::Debug {
    fn on_labeled(
        &mut self,
        model: &mut M,
        labeled: &LabeledSample,
        ts_ns: i64,
        current_mid: f64,
    ) -> Result<UpdateDecision>;
    fn updates(&self) -> usize;
}

#[derive(Debug, Default, Clone)]
pub struct NoopTrainer;

impl NoopTrainer {
    pub fn new() -> Self {
        Self
    }

    pub fn updates(&self) -> usize {
        0
    }
}

impl<M: AlphaModel> Trainer<M> for NoopTrainer {
    fn on_labeled(
        &mut self,
        _model: &mut M,
        _labeled: &LabeledSample,
        _ts_ns: i64,
        _current_mid: f64,
    ) -> Result<UpdateDecision> {
        Ok(UpdateDecision::Skip(UpdateReason::None))
    }

    fn updates(&self) -> usize {
        0
    }
}

#[derive(Debug, Clone)]
pub struct RlsTrainer {
    policy: UpdatePolicy,
    updates: usize,
}

impl RlsTrainer {
    pub fn new(config: UpdatePolicyConfig) -> Self {
        Self {
            policy: UpdatePolicy::from_config(config),
            updates: 0,
        }
    }

    pub fn updates(&self) -> usize {
        self.updates
    }
}

impl<M: AlphaModel> Trainer<M> for RlsTrainer {
    fn on_labeled(
        &mut self,
        model: &mut M,
        labeled: &LabeledSample,
        ts_ns: i64,
        current_mid: f64,
    ) -> Result<UpdateDecision> {
        let decision = self
            .policy
            .should_update(ts_ns, labeled.label_bps, current_mid);
        if let UpdateDecision::Apply { label_bps, .. } = decision {
            model.update(&labeled.sample.features, label_bps)?;
            self.updates += 1;
        }
        Ok(decision)
    }

    fn updates(&self) -> usize {
        self.updates
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result as AnyResult;
    use crate::alpha::AlphaModel;
    use crate::alpha::Sample;

    #[derive(Debug, Clone)]
    struct RecordingModel {
        dim: usize,
        last_label: f64,
        updates: usize,
    }

    impl RecordingModel {
        fn new(dim: usize) -> Self {
            Self {
                dim,
                last_label: 0.0,
                updates: 0,
            }
        }
    }

    impl AlphaModel for RecordingModel {
        fn predict(&self, x: &[f64]) -> AnyResult<f64> {
            if x.len() != self.dimension() {
                anyhow::bail!("feature dimension mismatch");
            }
            Ok(0.0)
        }

        fn update(&mut self, x: &[f64], y_bps: f64) -> AnyResult<()> {
            if x.len() != self.dimension() {
                anyhow::bail!("feature dimension mismatch");
            }
            self.last_label = y_bps;
            self.updates += 1;
            Ok(())
        }

        fn dimension(&self) -> usize {
            self.dim
        }

        fn weights(&self) -> &[f64] {
            &[]
        }
    }

    #[test]
    fn rls_trainer_applies_clip_and_counts() {
        let mut trainer = RlsTrainer::new(UpdatePolicyConfig {
            label_clip_bps: Some(1.0),
            ..UpdatePolicyConfig::default()
        });
        let mut model = RecordingModel::new(1);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 0.0,
            output_bps: 0.0,
        };
        let labeled = LabeledSample {
            sample,
            label_bps: 5.0,
            label_ts_ns: 1,
        };
        let decision = trainer
            .on_labeled(&mut model, &labeled, 1, 100.0)
            .unwrap();
        match decision {
            UpdateDecision::Apply { label_bps, .. } => {
                assert!((label_bps - 1.0).abs() < 1e-9);
            }
            _ => panic!("expected apply"),
        }
        assert_eq!(trainer.updates(), 1);
        assert!((model.last_label - 1.0).abs() < 1e-9);
    }

    #[test]
    fn noop_trainer_skips_updates() {
        let mut trainer = NoopTrainer::new();
        let mut model = RecordingModel::new(1);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 0.0,
            output_bps: 0.0,
        };
        let labeled = LabeledSample {
            sample,
            label_bps: 2.0,
            label_ts_ns: 1,
        };

        let decision = trainer
            .on_labeled(&mut model, &labeled, 1, 100.0)
            .unwrap();
        match decision {
            UpdateDecision::Skip(_) => {}
            _ => panic!("expected skip"),
        }
        assert_eq!(trainer.updates(), 0);
        assert_eq!(model.updates, 0);
    }
}
