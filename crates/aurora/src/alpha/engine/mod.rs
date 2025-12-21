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

mod feature_runtime;
mod policies;

use std::sync::Arc;

use anyhow::{Result, anyhow, bail};
use nautilus_model::{data::TradeTick, orderbook::OrderBook};

use crate::alpha::AlphaModel;
use crate::alpha::features::{FeatureInputs, lookup_feature};
use crate::alpha::metrics::{AlphaMetrics, VersionedAlphaMetrics};
use crate::alpha::training::{Labeler, LabeledSample, RlsTrainer, Sample, Trainer};

use self::feature_runtime::{FeatureHandle, FeatureState};
pub use self::policies::{
    OutputDecision, OutputPolicy, PredictPolicyConfig, SampleDecision, SamplePolicy,
    SamplePolicyConfig, SampleReason, TriggerLogic,
};
pub use crate::alpha::training::{UpdateDecision, UpdatePolicy, UpdatePolicyConfig, UpdateReason};

#[derive(Debug)]
pub struct AlphaEngine<M: AlphaModel> {
    model: M,
    // Per-feature indicator states + mapping to output slots.
    feature_states: Vec<FeatureState>,
    feature_handles: Vec<FeatureHandle>,
    feature_names: Vec<String>,
    feature_buf: Vec<f64>,
    feature_pool: Vec<Vec<f64>>,
    tick_size: f64,
    i_max: f64,
    labeler: Labeler,
    sample_policy: SamplePolicy,
    output_policy: OutputPolicy,
    trainer: Box<dyn Trainer<M>>,
    snapshot_since_last: usize,
    last_alpha_bps: f64,
    base_sigma: f64,
    metrics: VersionedAlphaMetrics,
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
    pub fn new_with_model_and_trainer(
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
        feature_names: Option<Vec<String>>,
        trainer: Box<dyn Trainer<M>>,
    ) -> Result<Self> {
        let names = Self::resolve_feature_names(feature_names)?;
        Self::init_with_trainer(
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
            names,
            trainer,
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
    pub fn new_with_ctor_and_trainer(
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
        feature_names: Option<Vec<String>>,
        trainer: Box<dyn Trainer<M>>,
    ) -> Result<Self> {
        let names = Self::resolve_feature_names(feature_names)?;
        let total_dim: usize = names.len();
        let model = model_ctor(total_dim)?;
        Self::init_with_trainer(
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
            names,
            trainer,
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
        let trainer = Box::new(RlsTrainer::new(update_cfg));
        Self::init_with_trainer(
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
            feature_names,
            trainer,
        )
    }

    #[allow(clippy::too_many_arguments)]
    fn init_with_trainer(
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
        feature_names: Vec<String>,
        trainer: Box<dyn Trainer<M>>,
    ) -> Result<Self> {
        let total_dim: usize = feature_names.len();
        Self::validate_dimension(&model, total_dim)?;
        let queue_cap = max_queue_len.max(1);
        let (feature_states, feature_handles) = Self::build_features(&feature_names)?;
        Ok(Self {
            model,
            feature_states,
            feature_handles,
            feature_names,
            feature_buf: vec![0.0; total_dim],
            feature_pool: Vec::with_capacity(queue_cap),
            tick_size: tick_size.max(1e-9),
            i_max: i_max.max(1e-9),
            labeler: Labeler::new(lag_ns, queue_cap),
            sample_policy: SamplePolicy {
                time_stride_ns: time_stride_ns.max(0),
                count_stride,
                mid_move_bps: predict_cfg.mid_move_bps,
                sigma_jump: predict_cfg.sigma_jump,
                inventory_delta: predict_cfg.inventory_delta,
                require_mid_valid: predict_cfg.require_mid_valid,
                trigger_logic: predict_cfg.trigger_logic,
                last_trigger_ns: 0,
                last_trigger_mid: 0.0,
            },
            output_policy: OutputPolicy::new(min_updates_for_output),
            trainer,
            snapshot_since_last: 0,
            last_alpha_bps: 0.0,
            base_sigma: base_sigma.max(0.0),
            metrics: VersionedAlphaMetrics::new("default"),
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

        let decision = self.sample_policy.should_sample(
            ts_ns,
            mid,
            inputs.base_sigma,
            inputs.inventory_qty,
            self.snapshot_since_last,
        );
        if matches!(decision, SampleDecision::Skip(_)) {
            let labeled = self.labeler.on_market(ts_ns, mid)?;
            self.process_labeled_samples(labeled, ts_ns, mid)?;
            self.snapshot_since_last += 1;
            return Ok(self.last_alpha_bps);
        }

        Self::write_features(
            &self.feature_handles,
            &self.feature_states,
            &mut self.feature_buf,
            &inputs,
        );

        let pred_bps = self.model.predict(&self.feature_buf)?;
        let updates = self.trainer.updates();
        let output_decision = self.output_policy.decide(updates, pred_bps);
        let output_bps = if output_decision.emit {
            output_decision.output_bps
        } else {
            self.last_alpha_bps
        };

        let labeled = self.labeler.on_market(ts_ns, mid)?;
        self.process_labeled_samples(labeled, ts_ns, mid)?;
        let sample = self.build_sample(ts_ns, mid, pred_bps, output_bps);
        self.labeler.enqueue(sample)?;
        let labeled = self.labeler.on_market(ts_ns, mid)?;
        self.process_labeled_samples(labeled, ts_ns, mid)?;
        if output_decision.emit {
            self.last_alpha_bps = output_decision.output_bps;
        }

        self.snapshot_since_last = 0;
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

        let decision = self.sample_policy.should_sample(
            ts_ns,
            mid,
            inputs.base_sigma,
            inputs.inventory_qty,
            self.snapshot_since_last,
        );
        if matches!(decision, SampleDecision::Skip(_)) {
            let labeled = self.labeler.on_market(ts_ns, mid)?;
            self.process_labeled_samples(labeled, ts_ns, mid)?;
            self.snapshot_since_last += 1;
            return Ok(Some(self.last_alpha_bps));
        }

        Self::write_features(
            &self.feature_handles,
            &self.feature_states,
            &mut self.feature_buf,
            &inputs,
        );

        let pred_bps = self.model.predict(&self.feature_buf)?;
        let updates = self.trainer.updates();
        let output_decision = self.output_policy.decide(updates, pred_bps);
        let output_bps = if output_decision.emit {
            output_decision.output_bps
        } else {
            self.last_alpha_bps
        };

        let labeled = self.labeler.on_market(ts_ns, mid)?;
        self.process_labeled_samples(labeled, ts_ns, mid)?;
        let sample = self.build_sample(ts_ns, mid, pred_bps, output_bps);
        self.labeler.enqueue(sample)?;
        let labeled = self.labeler.on_market(ts_ns, mid)?;
        self.process_labeled_samples(labeled, ts_ns, mid)?;
        if output_decision.emit {
            self.last_alpha_bps = output_decision.output_bps;
        }

        self.snapshot_since_last = 0;
        Ok(Some(self.last_alpha_bps))
    }

    pub fn metrics(&self) -> &AlphaMetrics {
        self.metrics.current_metrics()
    }

    pub fn metrics_versioned(&self) -> &VersionedAlphaMetrics {
        &self.metrics
    }

    pub fn model_version(&self) -> &str {
        self.metrics.current_version()
    }

    pub fn set_model_version(&mut self, version: impl Into<Arc<str>>, reset: bool) {
        self.metrics.set_version(version, reset);
    }

    pub fn reset_metrics(&mut self) {
        self.metrics.reset_current();
    }

    pub fn reset_metrics_all(&mut self) {
        self.metrics.reset_all();
    }

    pub fn feature_names(&self) -> &[String] {
        &self.feature_names
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

    fn build_sample(&mut self, ts_ns: i64, mid: f64, pred_bps: f64, output_bps: f64) -> Sample {
        let mut buf = self
            .feature_pool
            .pop()
            .unwrap_or_else(|| vec![0.0; self.feature_buf.len()]);
        if buf.len() != self.feature_buf.len() {
            buf.resize(self.feature_buf.len(), 0.0);
        }
        buf.copy_from_slice(&self.feature_buf);
        Sample {
            ts_ns,
            mid,
            features: buf,
            pred_bps,
            output_bps,
        }
    }

    fn process_labeled_samples(
        &mut self,
        labeled: Vec<LabeledSample>,
        ts_ns: i64,
        current_mid: f64,
    ) -> Result<()> {
        for labeled_sample in labeled {
            let label_bps = labeled_sample.label_bps;
            let pred_bps = labeled_sample.sample.pred_bps;
            let output_bps = labeled_sample.sample.output_bps;
            self.metrics.update(pred_bps, output_bps, label_bps);

            let decision = self
                .trainer
                .on_labeled(&mut self.model, &labeled_sample, ts_ns, current_mid);
            let Sample { features, .. } = labeled_sample.sample;
            self.feature_pool.push(features);
            decision?;
        }
        Ok(())
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
    use crate::alpha::{ArcSwapModelHandle, NoopTrainer, Predictor, RlsAlpha, RlsParams, SwappableModel};
    use std::sync::Arc;

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
        assert_eq!(engine.sample_policy.last_trigger_ns, 2);
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
        assert_eq!(engine.sample_policy.last_trigger_ns, 1);

        // Small mid move (<10 bps) should not trigger.
        let deltas2 = snapshot(&instrument_id, 100.05, 100.05); // 5 bps move
        book.apply_deltas(&deltas2).unwrap();
        let _ = engine.handle_order_book(2, &book, 0.0).unwrap();
        assert_eq!(engine.sample_policy.last_trigger_ns, 1);

        // Large mid move (>10 bps) should trigger.
        let deltas3 = snapshot(&instrument_id, 101.5, 101.5); // 150 bps move
        book.apply_deltas(&deltas3).unwrap();
        let _ = engine.handle_order_book(3, &book, 0.0).unwrap();
        assert_eq!(engine.sample_policy.last_trigger_ns, 3);
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
    fn labels_process_when_predict_skips() {
        let instrument_id = InstrumentId::from("TEST.SKIPLABEL");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let model = RecordingModel::new(1);
        let predict_cfg = PredictPolicyConfig {
            mid_move_bps: Some(1e9),
            ..PredictPolicyConfig::default()
        };
        let mut engine = AlphaEngine::new_with_model(
            1,    // lag
            0.01,
            1.0,
            model,
            0,    // time_stride_ns disabled
            0,    // count_stride disabled
            0,
            16,
            0.0,
            predict_cfg,
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

        let rec = &engine.model;
        assert_eq!(rec.updates, 1);
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

    #[test]
    fn engine_supports_swappable_model_handle() {
        #[derive(Debug)]
        struct DummyPredictor {
            value: f64,
        }

        impl Predictor for DummyPredictor {
            fn predict(&self, _x: &[f64]) -> AnyResult<f64> {
                Ok(self.value)
            }

            fn dimension(&self) -> usize {
                1
            }

            fn version(&self) -> &str {
                "dummy"
            }
        }

        let instrument_id = InstrumentId::from("TEST.SWAP");
        let mut book = OrderBook::new(instrument_id.clone(), BookType::L2_MBP);
        let handle = Arc::new(ArcSwapModelHandle::new(Arc::new(DummyPredictor { value: 1.0 })));
        let model = SwappableModel::new(handle.clone());
        let trainer: Box<dyn Trainer<SwappableModel>> = Box::new(NoopTrainer::new());
        let mut engine = AlphaEngine::new_with_model_and_trainer(
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
            Some(vec!["test_shared_book".to_string()]),
            trainer,
        )
        .expect("engine init");

        let deltas1 = snapshot(&instrument_id, 100.0, 100.0);
        book.apply_deltas(&deltas1).unwrap();
        let alpha1 = engine.handle_order_book(1, &book, 0.0).unwrap();
        assert!((alpha1 - 1.0).abs() < 1e-9);

        handle.swap(Arc::new(DummyPredictor { value: 2.0 }));
        let deltas2 = snapshot(&instrument_id, 101.0, 101.0);
        book.apply_deltas(&deltas2).unwrap();
        let alpha2 = engine.handle_order_book(2, &book, 0.0).unwrap();
        assert!((alpha2 - 2.0).abs() < 1e-9);
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
