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

//! Sampling and output policies for AlphaEngine.

/// Lightweight sampling policy: zero allocation, defaults mimic legacy behavior.
#[derive(Debug, Clone)]
pub struct SamplePolicy {
    pub time_stride_ns: i64,          // 0 disables time-based triggering
    pub count_stride: usize,          // 0 disables count-based triggering; 1 means every event triggers
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
pub enum SampleDecision {
    Trigger(SampleReason),
    Skip(SampleReason),
}

#[derive(Debug, Clone, Copy)]
pub enum SampleReason {
    None,
    TimeStride,
    CountStride,
    MidMove,
    SigmaJump,
    InventoryDelta,
    MidInvalid,
}

#[derive(Debug, Clone)]
pub struct SamplePolicyConfig {
    pub mid_move_bps: Option<f64>,
    pub sigma_jump: Option<f64>,
    pub inventory_delta: Option<f64>,
    pub require_mid_valid: bool,
    pub trigger_logic: TriggerLogic,
}

pub type PredictPolicyConfig = SamplePolicyConfig;

impl Default for SamplePolicyConfig {
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

impl SamplePolicy {
    pub fn new(time_stride_ns: i64, count_stride: usize) -> Self {
        Self {
            time_stride_ns,
            count_stride,
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
    pub fn should_sample(
        &mut self,
        ts_ns: i64,
        mid: f64,
        sigma: f64,
        inventory: f64,
        snapshots_since_last: usize,
    ) -> SampleDecision {
        if self.require_mid_valid && mid <= 0.0 {
            return SampleDecision::Skip(SampleReason::MidInvalid);
        }

        let time_enabled = self.time_stride_ns > 0;
        let count_enabled = self.count_stride > 0;
        let mid_enabled = self.mid_move_bps.is_some();
        let sigma_enabled = self.sigma_jump.is_some();
        let inv_enabled = self.inventory_delta.is_some();

        let time_ok = time_enabled && ts_ns - self.last_trigger_ns >= self.time_stride_ns;
        let count_ok = count_enabled && snapshots_since_last + 1 >= self.count_stride;

        let mid_ok = self.mid_move_bps.map_or(false, |thr| {
            if self.last_trigger_mid <= 0.0 || mid <= 0.0 {
                return true;
            }
            let move_bps = ((mid - self.last_trigger_mid) / self.last_trigger_mid) * 1e4;
            move_bps.abs() >= thr
        });

        let sigma_ok = self.sigma_jump.map_or(false, |thr| sigma.abs() >= thr);

        let inv_ok = self
            .inventory_delta
            .map_or(false, |thr| inventory.abs() >= thr);

        let mut any = false;
        let mut all = true;
        let mut enabled = 0;
        if time_enabled {
            enabled += 1;
            any |= time_ok;
            all &= time_ok;
        }
        if count_enabled {
            enabled += 1;
            any |= count_ok;
            all &= count_ok;
        }
        if mid_enabled {
            enabled += 1;
            any |= mid_ok;
            all &= mid_ok;
        }
        if sigma_enabled {
            enabled += 1;
            any |= sigma_ok;
            all &= sigma_ok;
        }
        if inv_enabled {
            enabled += 1;
            any |= inv_ok;
            all &= inv_ok;
        }

        let triggered = match self.trigger_logic {
            TriggerLogic::Any => any,
            TriggerLogic::All => enabled > 0 && all,
        };

        let mut reason = SampleReason::None;
        if triggered {
            // choose a primary reason for stats (order of precedence is coarse)
            reason = if time_ok {
                SampleReason::TimeStride
            } else if count_ok {
                SampleReason::CountStride
            } else if mid_ok {
                SampleReason::MidMove
            } else if sigma_ok {
                SampleReason::SigmaJump
            } else if inv_ok {
                SampleReason::InventoryDelta
            } else {
                SampleReason::None
            };
            self.last_trigger_ns = ts_ns;
            if mid > 0.0 {
                self.last_trigger_mid = mid;
            }
            return SampleDecision::Trigger(reason);
        }

        SampleDecision::Skip(reason)
    }
}

#[derive(Debug, Clone)]
pub struct OutputPolicy {
    pub min_updates_for_output: usize,
}

#[derive(Debug, Clone, Copy)]
pub struct OutputDecision {
    pub output_bps: f64,
    pub emit: bool,
}

impl OutputPolicy {
    pub fn new(min_updates_for_output: usize) -> Self {
        Self {
            min_updates_for_output,
        }
    }

    #[inline]
    pub fn decide(&mut self, updates: usize, pred_bps: f64) -> OutputDecision {
        if updates < self.min_updates_for_output {
            return OutputDecision {
                output_bps: 0.0,
                emit: true,
            };
        }
        OutputDecision {
            output_bps: pred_bps,
            emit: true,
        }
    }
}
