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

//! AlphaEngine orchestrates order book ingestion, feature construction, delayed labeling,
//! and alpha model predict/update in Rust to avoid Python hot-path overhead.

use std::collections::{HashMap, VecDeque};

use anyhow::{Result, anyhow, bail};
use nautilus_model::{data::TradeTick, orderbook::OrderBook};

use super::{
    AlphaModel,
    features::{FeatureEntry, FeatureInputs, lookup_feature},
};

/// Lightweight prediction trigger policy: zero allocation, defaults mimic legacy behavior.
#[derive(Debug, Clone)]
pub struct PredictPolicy {
    pub time_stride_ns: i64,          // 0 disables time-based triggering
    pub count_stride: usize,          // 1 means every event triggers
    pub min_updates_for_output: usize,
    pub mid_move_bps: Option<f64>,    // relative mid move threshold in bps; None to disable
    pub sigma_jump: Option<f64>,      // optional volatility jump trigger threshold
    pub inventory_delta: Option<f64>, // optional inventory magnitude trigger
    pub require_mid_valid: bool,      // if false, allows mid<=0 to still trigger
    pub trigger_logic: TriggerLogic,  // combine conditions with Any/All
    // state
    pub last_trigger_ns: i64,
    pub last_trigger_mid: f64,
}

#[derive(Debug, Clone, Copy)]
pub enum TriggerLogic {
    Any,
    All,
}

#[derive(Debug, Clone, Copy)]
pub enum PredictDecision {
    Trigger(PredictReason),
    Skip(PredictReason),
}

#[derive(Debug, Clone, Copy)]
pub enum PredictReason {
    None,
    TimeStride,
    CountStride,
    MidMove,
    SigmaJump,
    InventoryDelta,
    ColdStart,
    MidInvalid,
}

#[derive(Debug, Clone)]
pub struct PredictPolicyConfig {
    pub mid_move_bps: Option<f64>,
    pub sigma_jump: Option<f64>,
    pub inventory_delta: Option<f64>,
    pub require_mid_valid: bool,
    pub trigger_logic: TriggerLogic,
}

impl Default for PredictPolicyConfig {
    fn default() -> Self {
        Self {
            mid_move_bps: None,
            sigma_jump: None,
            inventory_delta: None,
            require_mid_valid: true,
            trigger_logic: TriggerLogic::Any,
        }
    }
}

impl PredictPolicy {
    pub fn new(
        time_stride_ns: i64,
        count_stride: usize,
        min_updates_for_output: usize,
    ) -> Self {
        Self {
            time_stride_ns,
            count_stride,
            min_updates_for_output,
            mid_move_bps: None,
            sigma_jump: None,
            inventory_delta: None,
            require_mid_valid: true,
            trigger_logic: TriggerLogic::Any,
            last_trigger_ns: 0,
            last_trigger_mid: 0.0,
        }
    }

    #[inline]
    pub fn should_predict(
        &mut self,
        ts_ns: i64,
        mid: f64,
        sigma: f64,
        inventory: f64,
        snapshots_since_last: usize,
        updates: usize,
    ) -> PredictDecision {
        if self.require_mid_valid && mid <= 0.0 {
            return PredictDecision::Skip(PredictReason::MidInvalid);
        }

        let time_ok = self.time_stride_ns == 0 || ts_ns - self.last_trigger_ns >= self.time_stride_ns;
        let count_ok = snapshots_since_last + 1 >= self.count_stride;

        let mid_ok = self.mid_move_bps.map_or(false, |thr| {
            if self.last_trigger_mid <= 0.0 || mid <= 0.0 {
                return true;
            }
            let move_bps = ((mid - self.last_trigger_mid) / self.last_trigger_mid) * 1e4;
            move_bps.abs() >= thr
        });

        let sigma_ok = self
            .sigma_jump
            .map_or(false, |thr| sigma.abs() >= thr);

        let inv_ok = self
            .inventory_delta
            .map_or(false, |thr| inventory.abs() >= thr);

        let any = time_ok || count_ok || mid_ok || sigma_ok || inv_ok;
        let all = [Some(time_ok), Some(count_ok), self.mid_move_bps.map(|_| mid_ok), self.sigma_jump.map(|_| sigma_ok), self.inventory_delta.map(|_| inv_ok)]
            .into_iter()
            .flatten()
            .all(|x| x);

        let triggered = match self.trigger_logic {
            TriggerLogic::Any => any,
            TriggerLogic::All => all,
        };

        let mut reason = PredictReason::None;
        if triggered {
            // choose a primary reason for stats (order of precedence is coarse)
            reason = if time_ok {
                PredictReason::TimeStride
            } else if count_ok {
                PredictReason::CountStride
            } else if mid_ok {
                PredictReason::MidMove
            } else if sigma_ok {
                PredictReason::SigmaJump
            } else if inv_ok {
                PredictReason::InventoryDelta
            } else {
                PredictReason::None
            };
            self.last_trigger_ns = ts_ns;
            if mid > 0.0 {
                self.last_trigger_mid = mid;
            }
            // Cold start: allow trigger but upper layer may zero output.
            if updates < self.min_updates_for_output {
                return PredictDecision::Trigger(PredictReason::ColdStart);
            }
            return PredictDecision::Trigger(reason);
        }

        PredictDecision::Skip(reason)
    }
}

/// Lightweight update policy: controls when to train, with optional sampling/clipping; defaults mimic legacy behavior.
#[derive(Debug, Clone)]
pub struct UpdatePolicy {
    pub lag_ns: i64,
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
    LagNotReached,
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
    pub fn new(lag_ns: i64) -> Self {
        Self {
            lag_ns,
            min_update_interval_ns: 0,
            count_stride: 1,
            sample_rate: 1.0,
            label_clip_bps: None,
            label_min_abs_bps: None,
            mid_required: true,
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

#[derive(Clone, Debug)]
struct FeatureSample {
    ts_ns: i64,
    mid: f64,
    features: Vec<f64>,
}

#[derive(Debug)]
pub struct AlphaEngine<M: AlphaModel> {
    model: M,
    // Per-feature indicator states + mapping to output slots.
    feature_states: Vec<FeatureState>,
    feature_handles: Vec<FeatureHandle>,
    feature_buf: Vec<f64>,
    lag_ns: i64,
    tick_size: f64,
    i_max: f64,
    // Delayed labeling queue to align features with future realized return.
    label_queue: VecDeque<FeatureSample>,
    max_queue_len: usize,
    predict_policy: PredictPolicy,
    update_policy: UpdatePolicy,
    snapshot_since_last: usize,
    last_alpha_bps: f64,
    updates: usize,
    base_sigma: f64,
}

impl<M: AlphaModel> AlphaEngine<M> {
    #[allow(clippy::too_many_arguments)]
    pub fn new_with_model(
        lag_ns: i64,
        tick_size: f64,
        i_max: f64,
        model: M,
        time_stride_ns: i64,
        count_stride: usize,
        min_updates_for_output: usize,
        max_queue_len: usize,
        base_sigma: f64,
        predict_cfg: PredictPolicyConfig,
        update_cfg: UpdatePolicyConfig,
        feature_names: Option<Vec<String>>,
    ) -> Result<Self> {
        let names = Self::resolve_feature_names(feature_names)?;
        Self::init(
            lag_ns,
            tick_size,
            i_max,
            model,
            time_stride_ns,
            count_stride,
            min_updates_for_output,
            max_queue_len,
            base_sigma,
            predict_cfg,
            update_cfg,
            names,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub fn new_with_ctor(
        lag_ns: i64,
        tick_size: f64,
        i_max: f64,
        model_ctor: impl FnOnce(usize) -> Result<M>,
        time_stride_ns: i64,
        count_stride: usize,
        min_updates_for_output: usize,
        max_queue_len: usize,
        base_sigma: f64,
        predict_cfg: PredictPolicyConfig,
        update_cfg: UpdatePolicyConfig,
        feature_names: Option<Vec<String>>,
    ) -> Result<Self> {
        let names = Self::resolve_feature_names(feature_names)?;
        let total_dim: usize = names.len();
        let model = model_ctor(total_dim)?;
        Self::init(
            lag_ns,
            tick_size,
            i_max,
            model,
            time_stride_ns,
            count_stride,
            min_updates_for_output,
            max_queue_len,
            base_sigma,
            predict_cfg,
            update_cfg,
            names,
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn init(
        lag_ns: i64,
        tick_size: f64,
        i_max: f64,
        model: M,
        time_stride_ns: i64,
        count_stride: usize,
        min_updates_for_output: usize,
        max_queue_len: usize,
        base_sigma: f64,
        predict_cfg: PredictPolicyConfig,
        update_cfg: UpdatePolicyConfig,
        feature_names: Vec<String>,
    ) -> Result<Self> {
        let total_dim: usize = feature_names.len();
        Self::validate_dimension(&model, total_dim)?;
        let queue_cap = max_queue_len.max(1);
        let (feature_states, feature_handles) = Self::build_features(&feature_names)?;
        Ok(Self {
            model,
            feature_states,
            feature_handles,
            feature_buf: vec![0.0; total_dim],
            lag_ns: lag_ns.max(0),
            tick_size: tick_size.max(1e-9),
            i_max: i_max.max(1e-9),
            label_queue: VecDeque::with_capacity(queue_cap),
            max_queue_len: queue_cap,
            predict_policy: PredictPolicy {
                time_stride_ns: time_stride_ns.max(0),
                count_stride: count_stride.max(1),
                min_updates_for_output,
                mid_move_bps: predict_cfg.mid_move_bps,
                sigma_jump: predict_cfg.sigma_jump,
                inventory_delta: predict_cfg.inventory_delta,
                require_mid_valid: predict_cfg.require_mid_valid,
                trigger_logic: predict_cfg.trigger_logic,
                last_trigger_ns: 0,
                last_trigger_mid: 0.0,
            },
            update_policy: UpdatePolicy {
                lag_ns: lag_ns.max(0),
                min_update_interval_ns: update_cfg.min_update_interval_ns.max(0),
                count_stride: update_cfg.count_stride.max(1),
                sample_rate: update_cfg.sample_rate.clamp(0.0, 1.0),
                label_clip_bps: update_cfg.label_clip_bps,
                label_min_abs_bps: update_cfg.label_min_abs_bps,
                mid_required: update_cfg.mid_required,
                last_update_ns: 0,
                since_last: 0,
                rng_state: 0x9E37_79B9_7F4A_7C15,
            },
            snapshot_since_last: 0,
            last_alpha_bps: 0.0,
            updates: 0,
            base_sigma: base_sigma.max(0.0),
        })
    }

    /// Evaluate on an externally maintained order book, return latest alpha prediction (bps).
    pub fn handle_order_book(
        &mut self,
        ts_ns: i64,
        book: &OrderBook,
        inventory_qty: f64,
    ) -> Result<f64> {
        let inputs = FeatureInputs {
            book,
            inventory_qty,
            tick_size: self.tick_size,
            i_max: self.i_max,
            base_sigma: self.base_sigma,
        };
        Self::update_features_on_book(&mut self.feature_states, inputs.book);
        let mid = Self::mid_price(inputs.book);

        if mid <= 0.0 {
            return Ok(self.last_alpha_bps);
        }

        let decision = self.predict_policy.should_predict(
            ts_ns,
            mid,
            inputs.base_sigma,
            inputs.inventory_qty,
            self.snapshot_since_last,
            self.updates,
        );
        if matches!(decision, PredictDecision::Skip(_)) {
            self.snapshot_since_last += 1;
            return Ok(self.last_alpha_bps);
        }

        Self::write_features(
            &self.feature_handles,
            &self.feature_states,
            &mut self.feature_buf,
            &inputs,
        );

        let alpha_bps = self.model.predict(&self.feature_buf)?;
        self.last_alpha_bps = match decision {
            PredictDecision::Trigger(PredictReason::ColdStart) => 0.0,
            _ => alpha_bps,
        };

        self.enqueue_sample(ts_ns, mid, self.feature_buf.clone());
        self.drain_labels(ts_ns, mid)?;

        self.snapshot_since_last = 0;
        self.predict_policy.last_trigger_ns = ts_ns;
        Ok(self.last_alpha_bps)
    }

    /// Optional trade handler (placeholder for future MO/cancel features).
    pub fn handle_trade(
        &mut self,
        ts_ns: i64,
        trade: &TradeTick,
        book: &OrderBook,
    ) -> Result<Option<f64>> {
        Self::update_features_on_trade(&mut self.feature_states, trade);
        let mid = Self::mid_price(book);
        let inputs = FeatureInputs {
            book,
            inventory_qty: 0.0,
            tick_size: self.tick_size,
            i_max: self.i_max,
            base_sigma: self.base_sigma,
        };
        if mid <= 0.0 {
            return Ok(Some(self.last_alpha_bps));
        }

        let decision = self.predict_policy.should_predict(
            ts_ns,
            mid,
            inputs.base_sigma,
            inputs.inventory_qty,
            self.snapshot_since_last,
            self.updates,
        );
        if matches!(decision, PredictDecision::Skip(_)) {
            self.snapshot_since_last += 1;
            return Ok(Some(self.last_alpha_bps));
        }

        Self::write_features(
            &self.feature_handles,
            &self.feature_states,
            &mut self.feature_buf,
            &inputs,
        );

        let alpha_bps = self.model.predict(&self.feature_buf)?;
        self.last_alpha_bps = match decision {
            PredictDecision::Trigger(PredictReason::ColdStart) => 0.0,
            _ => alpha_bps,
        };

        self.enqueue_sample(ts_ns, mid, self.feature_buf.clone());
        self.drain_labels(ts_ns, mid)?;

        self.snapshot_since_last = 0;
        self.predict_policy.last_trigger_ns = ts_ns;
        Ok(Some(self.last_alpha_bps))
    }

    fn mid_price(book: &OrderBook) -> f64 {
        match (book.best_bid_price(), book.best_ask_price()) {
            (Some(bid), Some(ask)) => (bid.as_f64() + ask.as_f64()) * 0.5,
            _ => 0.0,
        }
    }

    fn resolve_feature_names(feature_names: Option<Vec<String>>) -> Result<Vec<String>> {
        let default = vec!["imbalance", "micro_skew", "sigma_rel"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let names = feature_names.filter(|v| !v.is_empty()).unwrap_or(default);
        for name in &names {
            let canonical = name.replace('-', "_");
            lookup_feature(name)
                .or_else(|| lookup_feature(&canonical))
                .ok_or_else(|| anyhow!("unknown feature name '{name}'"))?;
        }
        Ok(names)
    }

    // Ensure caller-provided model matches the feature dimension derived from names.
    fn validate_dimension(model: &M, expected: usize) -> Result<()> {
        let actual = model.dimension();
        if actual != expected {
            bail!(
                "model dimension mismatch: expected {expected}, got {actual}"
            );
        }
        Ok(())
    }

    fn enqueue_sample(&mut self, ts_ns: i64, mid: f64, features: Vec<f64>) {
        if self.label_queue.len() >= self.max_queue_len {
            self.label_queue.pop_front();
        }
        self.label_queue.push_back(FeatureSample {
            ts_ns,
            mid,
            features,
        });
    }

    fn drain_labels(&mut self, ts_ns: i64, current_mid: f64) -> Result<()> {
        while let Some(front) = self.label_queue.front() {
            if ts_ns - front.ts_ns < self.lag_ns {
                break;
            }
            let sample = self.label_queue.pop_front().unwrap();
            if sample.mid <= 0.0 {
                continue;
            }
            // Label uses realized mid return after configured lag.
            let ret_bps = ((current_mid - sample.mid) / sample.mid) * 1e4;
            match self
                .update_policy
                .should_update(ts_ns, ret_bps, current_mid)
            {
                UpdateDecision::Apply { label_bps, .. } => {
                    self.model.update(&sample.features, label_bps)?;
                    self.updates += 1;
                }
                UpdateDecision::Skip(_) => {}
            }
        }
        Ok(())
    }
}

#[derive(Debug)]
// Backing indicator instance; may serve multiple feature names that share one source.
struct FeatureState {
    state: Box<dyn std::any::Any + Send + Sync>,
    on_book: Option<fn(&mut dyn std::any::Any, &OrderBook)>,
    on_trade: Option<fn(&mut dyn std::any::Any, &TradeTick)>,
}

#[derive(Debug)]
// Mapping from requested feature to its shared state and value function.
struct FeatureHandle {
    entry: &'static FeatureEntry,
    state_idx: usize,
}

impl<M: AlphaModel> AlphaEngine<M> {
    fn build_features(feature_names: &[String]) -> Result<(Vec<FeatureState>, Vec<FeatureHandle>)> {
        // Group by (source, type) so a single indicator instance can back multiple feature names
        // (e.g. L1 imbalance + micro_skew) while keeping book/trade callbacks unified.
        let mut states: Vec<FeatureState> = Vec::new();
        let mut handles: Vec<FeatureHandle> = Vec::new();
        let mut source_to_state: HashMap<&'static str, (std::any::TypeId, usize)> = HashMap::new();

        for name in feature_names {
            let canonical = name.replace('-', "_");
            let entry = lookup_feature(name.as_str())
                .or_else(|| lookup_feature(&canonical))
                .ok_or_else(|| anyhow!("unknown feature name '{name}'"))?;

            let state_idx = match source_to_state.get_mut(entry.source) {
                Some((ty, idx)) => {
                    if *ty != entry.type_id {
                        return Err(anyhow!(
                            "feature source '{}' registered with multiple types (existing={:?}, new={:?})",
                            entry.source,
                            ty,
                            entry.type_id
                        ));
                    }
                    let state = &mut states[*idx];
                    if state.on_book.is_none() && entry.on_book.is_some() {
                        state.on_book = entry.on_book;
                    }
                    if state.on_trade.is_none() && entry.on_trade.is_some() {
                        state.on_trade = entry.on_trade;
                    }
                    *idx
                }
                None => {
                    let idx = states.len();
                    states.push(FeatureState {
                        state: (entry.make)(),
                        on_book: entry.on_book,
                        on_trade: entry.on_trade,
                    });
                    source_to_state.insert(entry.source, (entry.type_id, idx));
                    idx
                }
            };

            handles.push(FeatureHandle { entry, state_idx });
        }

        Ok((states, handles))
    }

    fn update_features_on_book(states: &mut [FeatureState], book: &OrderBook) {
        for state in states {
            if let Some(on_book) = state.on_book {
                on_book(state.state.as_mut(), book);
            }
        }
    }

    fn update_features_on_trade(states: &mut [FeatureState], trade: &TradeTick) {
        for state in states {
            if let Some(on_trade) = state.on_trade {
                on_trade(state.state.as_mut(), trade);
            }
        }
    }

    fn write_features(
        handles: &[FeatureHandle],
        states: &[FeatureState],
        feature_buf: &mut [f64],
        inputs: &FeatureInputs,
    ) {
        debug_assert!(feature_buf.len() == handles.len());
        for (idx, handle) in handles.iter().enumerate() {
            let state = &states[handle.state_idx];
            feature_buf[idx] = (handle.entry.value)(state.state.as_ref(), inputs);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::{Result as AnyResult, bail};
    use nautilus_model::{
        data::{stubs::stub_trade_ethusdt_buyer, OrderBookDeltas},
        enums::BookType,
        identifiers::InstrumentId,
    };
    use crate::alpha::{RlsAlpha, RlsParams};

    #[test]
    fn shared_source_unions_callbacks() {
        let names = vec![
            "test_shared_book".to_string(),
            "test_shared_trade".to_string(),
        ];
        let (mut states, handles) =
            AlphaEngine::<RlsAlpha>::build_features(&names).expect("build features");

        let book = OrderBook::new(InstrumentId::from("TEST.TEST"), BookType::L2_MBP);
        let inputs = FeatureInputs {
            book: &book,
            inventory_qty: 0.0,
            tick_size: 0.01,
            i_max: 1.0,
            base_sigma: 0.0,
        };
        AlphaEngine::<RlsAlpha>::update_features_on_book(&mut states, inputs.book);

        let trade = stub_trade_ethusdt_buyer();
        AlphaEngine::<RlsAlpha>::update_features_on_trade(&mut states, &trade);

        let mut buf = vec![0.0; handles.len()];
        AlphaEngine::<RlsAlpha>::write_features(&handles, &states, &mut buf, &inputs);

        assert_eq!(buf.len(), 2);
        assert_eq!(buf[0], 1.0);
        assert_eq!(buf[1], 1.0);
        // ensure both callbacks share same state instance
        assert!(std::ptr::eq(
            states[handles[0].state_idx].state.as_ref(),
            states[handles[1].state_idx].state.as_ref()
        ));
    }

    #[test]
    fn engine_trains_on_book_updates() {
        let instrument_id = InstrumentId::from("TEST.TEST");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let params = RlsParams {
            a_max_bps: 1e6,
            ..Default::default()
        };
        let model = RlsAlpha::new(1, params).expect("model init");
        let mut engine = AlphaEngine::new_with_model(
            1,                 // lag_ns to defer label to next snapshot
            0.01,              // tick_size
            1.0,               // i_max
            model,
            0,                 // time_stride_ns
            1,                 // count_stride
            0,                 // min_updates_for_output
            16,                // max_queue_len
            0.0,               // base_sigma
            PredictPolicyConfig::default(),
            UpdatePolicyConfig::default(),
            Some(vec!["test_shared_book".to_string()]),
        )
        .expect("engine init");

        let deltas1 = snapshot(&instrument_id, 100.0, 100.0);
        book.apply_deltas(&deltas1).unwrap();
        let _ = engine.handle_order_book(1, &book, 0.0).unwrap();
        let deltas2 = snapshot(&instrument_id, 101.0, 101.0);
        book.apply_deltas(&deltas2).unwrap();
        let _ = engine.handle_order_book(2, &book, 0.0).unwrap();
        let deltas3 = snapshot(&instrument_id, 102.0, 102.0);
        book.apply_deltas(&deltas3).unwrap();
        let alpha3 = engine.handle_order_book(3, &book, 0.0).unwrap();

        // By the third snapshot, the first sample has been labeled with a positive return,
        // so the model should have learned a non-zero weight and emit a positive alpha.
        assert!(alpha3 > 0.0);
    }

    #[test]
    fn trade_event_triggers_evaluation() {
        let instrument_id = InstrumentId::from("TEST.TRADE");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let params = RlsParams {
            a_max_bps: 1e6,
            ..Default::default()
        };
        let model = RlsAlpha::new(2, params).expect("model init");
        let mut engine = AlphaEngine::new_with_model(
            1,
            0.01,
            1.0,
            model,
            0,
            1, // every event triggers
            0,
            16,
            0.0,
            PredictPolicyConfig::default(),
            UpdatePolicyConfig::default(),
            Some(vec![
                "test_shared_book".to_string(),
                "test_shared_trade".to_string(),
            ]),
        )
        .expect("engine init");

        // Seed book so mid is valid.
        let deltas = snapshot(&instrument_id, 100.0, 100.0);
        book.apply_deltas(&deltas).unwrap();
        let _ = engine.handle_order_book(1, &book, 0.0).unwrap();

        // Trade should update shared state and trigger evaluation with updated timestamp.
        let trade = stub_trade_ethusdt_buyer();
        let _ = engine.handle_trade(2, &trade, &book).unwrap();
        assert_eq!(engine.predict_policy.last_trigger_ns, 2);
        // trade callback increments trade_called; value function returns that counter.
        let trade_state = &engine.feature_states[engine.feature_handles[1].state_idx];
        let shared = trade_state
            .state
            .downcast_ref::<crate::alpha::features::tests::TestSharedIndicator>()
            .unwrap();
        assert_eq!(shared.trade_called, 1);
    }

    #[derive(Debug, Clone)]
    struct DummyModel {
        weights: Vec<f64>,
    }

    impl DummyModel {
        fn new(dim: usize) -> Self {
            Self {
                weights: vec![0.0; dim],
            }
        }
    }

    impl AlphaModel for DummyModel {
        fn predict(&self, x: &[f64]) -> AnyResult<f64> {
            if x.len() != self.dimension() {
                bail!(
                    "feature dimension mismatch: expected {}, got {}",
                    self.dimension(),
                    x.len()
                );
            }
            Ok(0.0)
        }

        fn update(&mut self, x: &[f64], _y_bps: f64) -> AnyResult<()> {
            if x.len() != self.dimension() {
                bail!(
                    "feature dimension mismatch: expected {}, got {}",
                    self.dimension(),
                    x.len()
                );
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

    #[test]
    fn new_with_model_rejects_dimension_mismatch() {
        let _instrument_id = InstrumentId::from("TEST.MISMATCH");
        let model = DummyModel::new(1);
        let result = AlphaEngine::new_with_model(
            1,
            0.01,
            1.0,
            model,
            0,
            1,
            0,
            16,
            0.0,
            PredictPolicyConfig::default(),
            UpdatePolicyConfig::default(),
            Some(vec![
                "test_shared_book".to_string(),
                "test_shared_trade".to_string(),
            ]),
        );
        assert!(result.is_err());
    }

    #[test]
    fn predict_triggers_on_mid_move_threshold() {
        let instrument_id = InstrumentId::from("TEST.MIDMOVE");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let params = RlsParams {
            a_max_bps: 1e6,
            ..Default::default()
        };
        let model = RlsAlpha::new(1, params).expect("model init");
        let predict_cfg = PredictPolicyConfig {
            mid_move_bps: Some(10.0), // 10 bps threshold
            ..PredictPolicyConfig::default()
        };
        let mut engine = AlphaEngine::new_with_model(
            1,
            0.01,
            1.0,
            model,
            1_000_000_000, // time_stride_ns (large to rely on mid trigger after first)
            100,           // count_stride large to rely on mid trigger
            0,
            16,
            0.0,
            predict_cfg,
            UpdatePolicyConfig::default(),
            Some(vec!["test_shared_book".to_string()]),
        )
        .expect("engine init");

        // First snapshot triggers (cold start), sets baseline mid=100.
        let deltas1 = snapshot(&instrument_id, 100.0, 100.0);
        book.apply_deltas(&deltas1).unwrap();
        let _ = engine.handle_order_book(1, &book, 0.0).unwrap();
        assert_eq!(engine.predict_policy.last_trigger_ns, 1);

        // Small mid move (<10 bps) should not trigger.
        let deltas2 = snapshot(&instrument_id, 100.05, 100.05); // 5 bps move
        book.apply_deltas(&deltas2).unwrap();
        let _ = engine.handle_order_book(2, &book, 0.0).unwrap();
        assert_eq!(engine.predict_policy.last_trigger_ns, 1);

        // Large mid move (>10 bps) should trigger.
        let deltas3 = snapshot(&instrument_id, 101.5, 101.5); // 150 bps move
        book.apply_deltas(&deltas3).unwrap();
        let _ = engine.handle_order_book(3, &book, 0.0).unwrap();
        assert_eq!(engine.predict_policy.last_trigger_ns, 3);
    }

    #[derive(Debug, Clone)]
    struct RecordingModel {
        dim: usize,
        weights: Vec<f64>,
        last_label: f64,
        updates: usize,
    }

    impl RecordingModel {
        fn new(dim: usize) -> Self {
            Self {
                dim,
                weights: vec![0.0; dim],
                last_label: 0.0,
                updates: 0,
            }
        }
    }

    impl AlphaModel for RecordingModel {
        fn predict(&self, x: &[f64]) -> AnyResult<f64> {
            if x.len() != self.dimension() {
                bail!(
                    "feature dimension mismatch: expected {}, got {}",
                    self.dimension(),
                    x.len()
                );
            }
            Ok(0.0)
        }

        fn update(&mut self, x: &[f64], y_bps: f64) -> AnyResult<()> {
            if x.len() != self.dimension() {
                bail!(
                    "feature dimension mismatch: expected {}, got {}",
                    self.dimension(),
                    x.len()
                );
            }
            self.last_label = y_bps;
            self.updates += 1;
            Ok(())
        }

        fn dimension(&self) -> usize {
            self.dim
        }

        fn weights(&self) -> &[f64] {
            &self.weights
        }
    }

    #[test]
    fn update_policy_clips_labels() {
        let instrument_id = InstrumentId::from("TEST.UPDATE");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let model = RecordingModel::new(1);
        let mut engine = AlphaEngine::new_with_model(
            1,    // lag
            0.01,
            1.0,
            model,
            0,
            1,
            0,
            16,
            0.0,
            PredictPolicyConfig::default(),
            UpdatePolicyConfig {
                label_clip_bps: Some(1.0), // clip labels to +/-1 bps
                ..UpdatePolicyConfig::default()
            },
            Some(vec!["test_shared_book".to_string()]),
        )
        .expect("engine init");

        // First snapshot seeds queue.
        let deltas1 = snapshot(&instrument_id, 100.0, 100.0);
        book.apply_deltas(&deltas1).unwrap();
        let _ = engine.handle_order_book(1, &book, 0.0).unwrap();
        // Second snapshot produces large positive return; should be clipped to 1.0 bps.
        let deltas2 = snapshot(&instrument_id, 110.0, 110.0);
        book.apply_deltas(&deltas2).unwrap();
        let _ = engine.handle_order_book(2, &book, 0.0).unwrap();

        let rec = &engine.model;
        assert_eq!(rec.updates, 1);
        assert!((rec.last_label - 1.0).abs() < 1e-9);
    }

    fn snapshot(instrument_id: &InstrumentId, bid: f64, ask: f64) -> OrderBookDeltas {
        use nautilus_model::{
            data::{order::BookOrder, OrderBookDelta, OrderBookDeltas},
            enums::{BookAction, OrderSide},
            types::{price::Price, quantity::Quantity},
        };
        let flags = 0;
        let sequence = 0;
        let ts_event = 1;
        let ts_init = 1;
        let id = instrument_id.clone();
        OrderBookDeltas::new(
            id,
            vec![
                OrderBookDelta::clear(id, sequence, ts_event.into(), ts_init.into()),
                OrderBookDelta::new(
                    id,
                    BookAction::Add,
                    BookOrder::new(
                        OrderSide::Buy,
                        Price::new(bid, 2),
                        Quantity::from("1"),
                        1,
                    ),
                    flags,
                    sequence,
                    ts_event.into(),
                    ts_init.into(),
                ),
                OrderBookDelta::new(
                    id,
                    BookAction::Add,
                    BookOrder::new(
                        OrderSide::Sell,
                        Price::new(ask, 2),
                        Quantity::from("1"),
                        2,
                    ),
                    flags,
                    sequence,
                    ts_event.into(),
                    ts_init.into(),
                ),
            ],
        )
    }
}
