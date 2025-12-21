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

//! Online metrics for alpha prediction quality.

use std::collections::HashMap;
use std::sync::Arc;

#[derive(Debug, Default, Clone)]
pub struct OnlineCorr {
    n: u64,
    mean_x: f64,
    mean_y: f64,
    c: f64,
    m2x: f64,
    m2y: f64,
}

impl OnlineCorr {
    pub fn update(&mut self, x: f64, y: f64) {
        self.n += 1;
        let n = self.n as f64;
        let dx = x - self.mean_x;
        self.mean_x += dx / n;
        let dy = y - self.mean_y;
        self.mean_y += dy / n;
        self.c += dx * (y - self.mean_y);
        self.m2x += dx * (x - self.mean_x);
        self.m2y += dy * (y - self.mean_y);
    }

    pub fn count(&self) -> u64 {
        self.n
    }

    pub fn corr(&self) -> Option<f64> {
        if self.n < 2 {
            return None;
        }
        if self.m2x <= 0.0 || self.m2y <= 0.0 {
            return None;
        }
        Some(self.c / (self.m2x * self.m2y).sqrt())
    }

    pub fn reset(&mut self) {
        *self = Self::default();
    }
}

#[derive(Debug, Default, Clone)]
pub struct AlphaMetrics {
    labeled_total: u64,
    pred_corr: OnlineCorr,
    output_corr: OnlineCorr,
}

impl AlphaMetrics {
    pub fn update(&mut self, pred_bps: f64, output_bps: f64, label_bps: f64) {
        if !label_bps.is_finite() {
            return;
        }
        if pred_bps.is_finite() {
            self.pred_corr.update(pred_bps, label_bps);
        }
        if output_bps.is_finite() {
            self.output_corr.update(output_bps, label_bps);
        }
        self.labeled_total += 1;
    }

    pub fn labeled_total(&self) -> u64 {
        self.labeled_total
    }

    pub fn pred_corr(&self) -> Option<f64> {
        self.pred_corr.corr()
    }

    pub fn output_corr(&self) -> Option<f64> {
        self.output_corr.corr()
    }

    pub fn reset(&mut self) {
        self.labeled_total = 0;
        self.pred_corr.reset();
        self.output_corr.reset();
    }
}

#[derive(Debug, Clone)]
pub struct VersionedAlphaMetrics {
    current: Arc<str>,
    buckets: HashMap<Arc<str>, AlphaMetrics>,
}

impl VersionedAlphaMetrics {
    pub fn new(version: impl Into<Arc<str>>) -> Self {
        let version = version.into();
        let mut buckets = HashMap::new();
        buckets.insert(Arc::clone(&version), AlphaMetrics::default());
        Self { current: version, buckets }
    }

    pub fn current_version(&self) -> &str {
        &self.current
    }

    pub fn set_version(&mut self, version: impl Into<Arc<str>>, reset: bool) {
        let version = version.into();
        self.current = Arc::clone(&version);
        let entry = self.buckets.entry(version).or_default();
        if reset {
            entry.reset();
        }
    }

    pub fn update(&mut self, pred_bps: f64, output_bps: f64, label_bps: f64) {
        self.current_mut().update(pred_bps, output_bps, label_bps);
    }

    pub fn update_for(
        &mut self,
        version: &str,
        pred_bps: f64,
        output_bps: f64,
        label_bps: f64,
    ) {
        let entry = self.buckets.entry(Arc::from(version)).or_default();
        entry.update(pred_bps, output_bps, label_bps);
    }

    pub fn metrics_for(&self, version: &str) -> Option<&AlphaMetrics> {
        self.buckets.get(version)
    }

    pub fn current_metrics(&self) -> &AlphaMetrics {
        self.buckets
            .get(self.current.as_ref())
            .expect("current metrics bucket must exist")
    }

    pub fn reset_current(&mut self) {
        self.current_mut().reset();
    }

    pub fn reset_all(&mut self) {
        for metrics in self.buckets.values_mut() {
            metrics.reset();
        }
    }

    fn current_mut(&mut self) -> &mut AlphaMetrics {
        self.buckets
            .get_mut(self.current.as_ref())
            .expect("current metrics bucket must exist")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn online_corr_perfect_positive() {
        let mut corr = OnlineCorr::default();
        corr.update(1.0, 1.0);
        corr.update(2.0, 2.0);
        corr.update(3.0, 3.0);
        let value = corr.corr().unwrap();
        assert!((value - 1.0).abs() < 1e-12);
    }

    #[test]
    fn online_corr_none_for_constant_series() {
        let mut corr = OnlineCorr::default();
        corr.update(1.0, 1.0);
        corr.update(1.0, 2.0);
        assert!(corr.corr().is_none());
    }

    #[test]
    fn alpha_metrics_tracks_counts_and_corr() {
        let mut metrics = AlphaMetrics::default();
        metrics.update(1.0, 1.0, 1.0);
        metrics.update(2.0, 2.0, 2.0);
        assert_eq!(metrics.labeled_total(), 2);
        assert!(metrics.pred_corr().unwrap() > 0.9);
        assert!(metrics.output_corr().unwrap() > 0.9);
    }

    #[test]
    fn versioned_metrics_isolate_versions() {
        let mut metrics = VersionedAlphaMetrics::new("v1");
        metrics.update(1.0, 1.0, 1.0);
        metrics.set_version("v2", false);
        metrics.update(2.0, 2.0, 2.0);

        let v1 = metrics.metrics_for("v1").unwrap();
        let v2 = metrics.metrics_for("v2").unwrap();
        assert_eq!(v1.labeled_total(), 1);
        assert_eq!(v2.labeled_total(), 1);
    }
}
