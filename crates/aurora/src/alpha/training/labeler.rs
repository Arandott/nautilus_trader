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

//! Labeler for delayed mid-return targets.

use std::collections::VecDeque;

use anyhow::{Result, bail};

#[derive(Debug, Clone)]
pub struct Sample {
    pub ts_ns: i64,
    pub mid: f64,
    pub features: Vec<f64>,
    pub pred_bps: f64,
    pub output_bps: f64,
}

#[derive(Debug, Clone)]
pub struct LabeledSample {
    pub sample: Sample,
    pub label_bps: f64,
    pub label_ts_ns: i64,
}

#[derive(Debug)]
pub struct Labeler {
    lag_ns: i64,
    max_queue_len: usize,
    queue: VecDeque<Sample>,
}

impl Labeler {
    pub fn new(lag_ns: i64, max_queue_len: usize) -> Self {
        let queue_cap = max_queue_len.max(1);
        Self {
            lag_ns: lag_ns.max(0),
            max_queue_len: queue_cap,
            queue: VecDeque::with_capacity(queue_cap),
        }
    }

    pub fn queue_len(&self) -> usize {
        self.queue.len()
    }

    pub fn on_market(&mut self, ts_ns: i64, mid_now: f64) -> Result<Vec<LabeledSample>> {
        self.drain(ts_ns, mid_now)
    }

    pub fn enqueue(&mut self, sample: Sample) -> Result<()> {
        if sample.mid <= 0.0 {
            bail!("sample mid invalid: {}", sample.mid);
        }
        if self.queue.len() >= self.max_queue_len {
            bail!(
                "label queue full (len={}, cap={}); increase label_queue_len or reduce sampling",
                self.queue.len(),
                self.max_queue_len
            );
        }
        self.queue.push_back(sample);
        Ok(())
    }

    fn drain(&mut self, ts_ns: i64, mid_now: f64) -> Result<Vec<LabeledSample>> {
        if !mid_now.is_finite() || mid_now <= 0.0 {
            return Ok(Vec::new());
        }
        let mut out = Vec::new();
        while let Some(front) = self.queue.front() {
            if ts_ns - front.ts_ns < self.lag_ns {
                break;
            }
            let sample = self.queue.pop_front().unwrap();
            if sample.mid <= 0.0 {
                continue;
            }
            let label_bps = ((mid_now - sample.mid) / sample.mid) * 1e4;
            out.push(LabeledSample {
                sample,
                label_bps,
                label_ts_ns: ts_ns,
            });
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn labeler_emits_after_lag() {
        let mut labeler = Labeler::new(2, 16);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 1.0,
            output_bps: 1.0,
        };

        labeler.enqueue(sample).unwrap();

        let out = labeler.on_market(1, 100.0).unwrap();
        assert!(out.is_empty());

        let out = labeler.on_market(2, 101.0).unwrap();
        assert!(out.is_empty());

        let out = labeler.on_market(3, 102.0).unwrap();
        assert_eq!(out.len(), 1);
        let labeled = &out[0];
        assert_eq!(labeled.label_ts_ns, 3);
        assert!((labeled.label_bps - 200.0).abs() < 1e-9);
    }

    #[test]
    fn labeler_lag_zero_labels_same_event() {
        let mut labeler = Labeler::new(0, 16);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 1.0,
            output_bps: 1.0,
        };

        labeler.enqueue(sample).unwrap();
        let out = labeler.on_market(1, 100.0).unwrap();
        assert_eq!(out.len(), 1);
        assert!((out[0].label_bps).abs() < 1e-12);
    }

    #[test]
    fn labeler_queue_full_errors() {
        let mut labeler = Labeler::new(10, 1);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 1.0,
            output_bps: 1.0,
        };
        labeler.enqueue(sample).unwrap();

        let second = Sample {
            ts_ns: 2,
            mid: 101.0,
            features: vec![2.0],
            pred_bps: 1.0,
            output_bps: 1.0,
        };
        let result = labeler.enqueue(second);
        assert!(result.is_err());
    }

    #[test]
    fn labeler_ignores_invalid_mid_until_valid() {
        let mut labeler = Labeler::new(2, 16);
        let sample = Sample {
            ts_ns: 1,
            mid: 100.0,
            features: vec![1.0],
            pred_bps: 1.0,
            output_bps: 1.0,
        };
        labeler.enqueue(sample).unwrap();

        let out = labeler.on_market(3, 0.0).unwrap();
        assert!(out.is_empty());
        assert_eq!(labeler.queue_len(), 1);

        let out = labeler.on_market(3, 101.0).unwrap();
        assert_eq!(out.len(), 1);
    }
}
