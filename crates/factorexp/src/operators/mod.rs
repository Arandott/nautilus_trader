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

//! High-performance rolling operators for factor expressions.

pub mod ma;
pub mod pair_rolling;
pub mod rolling;
pub mod stats;

use crate::buffer::RollingBuffer;
use std::fmt::Debug;

/// Common trait for all rolling operators.
pub trait RollingOperator: Send + Sync + Debug {
    /// Returns the name of the operator.
    fn name(&self) -> &str;

    /// Returns the window size.
    fn window_size(&self) -> usize;

    /// Returns true if the operator has received enough data.
    fn is_ready(&self) -> bool;

    /// Returns the current computed value.
    fn value(&self) -> f64;

    /// Updates the operator with a new value.
    fn update(&mut self, value: f64);

    /// Resets the operator to its initial state.
    fn reset(&mut self);

    /// Returns the total count of values processed.
    fn count(&self) -> usize;
}

/// Base implementation for rolling operators.
#[derive(Debug)]
pub struct BaseOperator {
    name: String,
    buffer: RollingBuffer,
    value: f64,
    valid_count: usize,
    last_valid_value: Option<f64>,
}

impl BaseOperator {
    /// Creates a new base operator.
    pub fn new(name: impl Into<String>, window_size: usize) -> Self {
        Self {
            name: name.into(),
            buffer: RollingBuffer::new(window_size),
            value: f64::NAN,
            valid_count: 0,
            last_valid_value: None,
        }
    }

    /// Returns a reference to the internal buffer.
    #[inline]
    pub fn buffer(&self) -> &RollingBuffer {
        &self.buffer
    }

    /// Returns a mutable reference to the internal buffer.
    #[inline]
    pub fn buffer_mut(&mut self) -> &mut RollingBuffer {
        &mut self.buffer
    }

    /// Sets the current value.
    #[inline]
    pub fn set_value(&mut self, value: f64) {
        self.value = value;
        self.last_valid_value = Some(value);
    }
    
    /// Gets the valid count.
    #[inline]
    pub fn valid_count(&self) -> usize {
        self.valid_count
    }
    
    /// Increments the valid count.
    #[inline]
    pub fn increment_valid_count(&mut self) {
        self.valid_count += 1;
    }
    
    /// Gets the last valid value.
    #[inline]
    pub fn last_valid_value(&self) -> Option<f64> {
        self.last_valid_value
    }
}

/// Macro to implement common RollingOperator methods.
#[macro_export]
macro_rules! impl_rolling_operator_common {
    ($type:ty) => {
        impl RollingOperator for $type {
            #[inline]
            fn name(&self) -> &str {
                &self.base.name
            }

            #[inline]
            fn window_size(&self) -> usize {
                self.base.buffer.window_size()
            }

            #[inline]
            fn is_ready(&self) -> bool {
                self.base.valid_count >= self.base.buffer.window_size()
            }

            #[inline]
            fn value(&self) -> f64 {
                if self.is_ready() {
                    self.base.value
                } else {
                    f64::NAN
                }
            }

            #[inline]
            fn update(&mut self, value: f64) {
                self.update_internal(value);
            }

            #[inline]
            fn count(&self) -> usize {
                self.base.buffer.count()
            }

            fn reset(&mut self) {
                self.base.buffer.reset();
                self.base.value = f64::NAN;
                self.base.valid_count = 0;
                self.base.last_valid_value = None;
            }
        }
    };
}

/// Factory function to create pair rolling operators by name.
pub fn get_pair_rolling_operator(name: &str, window_size: usize) -> Option<Box<dyn pair_rolling::PairRollingOperator>> {
    match name {
        "TS_Corr" => Some(Box::new(pair_rolling::Correlation::new(window_size))),
        "TS_Cov" => Some(Box::new(pair_rolling::Covariance::new(window_size, 1))),
        "TS_Beta" => Some(Box::new(pair_rolling::Beta::new(window_size, 1))),
        _ => None,
    }
}

/// Factory function to create rolling operators by name.
pub fn get_rolling_operator(name: &str, window_size: usize) -> Option<Box<dyn RollingOperator>> {
    match name {
        "TS_Mean" => Some(Box::new(rolling::Mean::new(window_size))),
        "TS_Sum" => Some(Box::new(rolling::Sum::new(window_size))),
        "TS_Min" => Some(Box::new(rolling::Min::new(window_size))),
        "TS_Max" => Some(Box::new(rolling::Max::new(window_size))),
        "TS_Std" => Some(Box::new(rolling::Std::new(window_size, 1))),
        "TS_Var" => Some(Box::new(rolling::Var::new(window_size, 1))),
        "TS_Med" | "TS_Median" => Some(Box::new(rolling::Median::new(window_size))),
        "TS_EMA" => Some(Box::new(ma::Ema::new(window_size))),
        "TS_WMA" => Some(Box::new(ma::Wma::new(window_size))),
        "TS_Skew" => Some(Box::new(stats::Skew::new(window_size))),
        "TS_Kurt" | "TS_Kurtosis" => Some(Box::new(stats::Kurtosis::new(window_size))),
        "TS_Mad" => Some(Box::new(stats::Mad::new(window_size))),
        "TS_Delta" => {
            // For TS_Delta, the window_size parameter is the period (lookback)
            // Delta always needs at least 2 values to compute difference
            let period = window_size;
            let actual_window_size = std::cmp::max(2, period + 1);
            Some(Box::new(rolling::Delta::new(actual_window_size)))
        },
        "TS_Ref" => {
            // For TS_Ref, the window_size parameter is actually the period (lookback)
            // Buffer needs to hold period + 1 values to look back 'period' positions
            let period = window_size;
            let actual_window_size = period + 1;
            Some(Box::new(rolling::Ref::new(actual_window_size, period)))
        },
        "TS_Rank" => Some(Box::new(rolling::Rank::new(window_size))),
        "TS_Argmax" => Some(Box::new(rolling::Argmax::new(window_size))),
        "TS_Argmin" => Some(Box::new(rolling::Argmin::new(window_size))),
        "TS_Product" => Some(Box::new(rolling::Product::new(window_size))),
        "ZScore" => Some(Box::new(rolling::ZScore::new(window_size, 0))),
        "Demean" => Some(Box::new(rolling::Demean::new(window_size))),
        _ => None,
    }
}