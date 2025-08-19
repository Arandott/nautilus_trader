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

//! Pair rolling statistical operators with O(1) complexity.
//!
//! This module implements rolling operators that work on two input series,
//! such as correlation, covariance, and beta coefficient.

use crate::{
    buffer::RollingBuffer,
    operators::BaseOperator,
};
use std::fmt::Debug;

/// Trait for pair rolling operators that process two input series.
pub trait PairRollingOperator: Send + Sync + Debug {
    /// Returns the name of the operator.
    fn name(&self) -> &str;

    /// Returns the window size.
    fn window_size(&self) -> usize;

    /// Returns true if the operator has received enough data.
    fn is_ready(&self) -> bool;

    /// Returns the current computed value.
    fn value(&self) -> f64;

    /// Updates the operator with new values from both series.
    fn update(&mut self, value1: f64, value2: f64);

    /// Resets the operator to its initial state.
    fn reset(&mut self);

    /// Returns the total count of values processed.
    fn count(&self) -> usize;
}

/// Base implementation for pair rolling operators with running statistics.
#[derive(Debug)]
pub struct PairBaseOperator {
    base: BaseOperator,
    buffer_x: RollingBuffer,
    buffer_y: RollingBuffer,
    // Running statistics for O(1) computation
    sum_x: f64,
    sum_y: f64,
    sum_xx: f64,
    sum_yy: f64,
    sum_xy: f64,
}

impl PairBaseOperator {
    /// Creates a new pair base operator.
    pub fn new(name: impl Into<String>, window_size: usize) -> Self {
        Self {
            base: BaseOperator::new(name, window_size),
            buffer_x: RollingBuffer::new(window_size),
            buffer_y: RollingBuffer::new(window_size),
            sum_x: 0.0,
            sum_y: 0.0,
            sum_xx: 0.0,
            sum_yy: 0.0,
            sum_xy: 0.0,
        }
    }

    /// Returns a reference to the base operator.
    #[inline]
    pub fn base(&self) -> &BaseOperator {
        &self.base
    }

    /// Returns a mutable reference to the base operator.
    #[inline]
    pub fn base_mut(&mut self) -> &mut BaseOperator {
        &mut self.base
    }

    /// Gets the valid count.
    #[inline]
    pub fn valid_count(&self) -> usize {
        self.base.valid_count()
    }

    /// Increments the valid count.
    #[inline]
    pub fn increment_valid_count(&mut self) {
        self.base.increment_valid_count();
    }

    /// Returns a reference to the X buffer.
    #[inline]
    pub fn buffer_x(&self) -> &RollingBuffer {
        &self.buffer_x
    }

    /// Returns a reference to the Y buffer.
    #[inline]
    pub fn buffer_y(&self) -> &RollingBuffer {
        &self.buffer_y
    }

    /// Returns the running sum of X values.
    #[inline]
    pub fn sum_x(&self) -> f64 {
        self.sum_x
    }

    /// Returns the running sum of Y values.
    #[inline]
    pub fn sum_y(&self) -> f64 {
        self.sum_y
    }

    /// Returns the running sum of X² values.
    #[inline]
    pub fn sum_xx(&self) -> f64 {
        self.sum_xx
    }

    /// Returns the running sum of Y² values.
    #[inline]
    pub fn sum_yy(&self) -> f64 {
        self.sum_yy
    }

    /// Returns the running sum of X*Y values.
    #[inline]
    pub fn sum_xy(&self) -> f64 {
        self.sum_xy
    }

    /// Updates running statistics with new values (O(1) operation).
    pub fn update_statistics(&mut self, x: f64, y: f64) {
        // Handle NaN inputs: skip if either value is NaN
        if x.is_nan() || y.is_nan() {
            return;
        }

        // Check if buffers are full and we need to subtract old values
        if self.buffer_x.is_full() {
            if let (Some(old_x), Some(old_y)) = (
                self.buffer_x.get(0), // Oldest value in buffer
                self.buffer_y.get(0),
            ) {
                // Subtract old values from running sums
                self.sum_x -= old_x;
                self.sum_y -= old_y;
                self.sum_xx -= old_x * old_x;
                self.sum_yy -= old_y * old_y;
                self.sum_xy -= old_x * old_y;
            }
        }

        // Add new values to buffers
        self.buffer_x.update(x);
        self.buffer_y.update(y);
        
        // Only increment valid count until we reach window size
        if self.base.valid_count() < self.buffer_x.window_size() {
            self.increment_valid_count();
        }

        // Add new values to running sums
        self.sum_x += x;
        self.sum_y += y;
        self.sum_xx += x * x;
        self.sum_yy += y * y;
        self.sum_xy += x * y;
    }

    /// Sets the computed value.
    #[inline]
    pub fn set_value(&mut self, value: f64) {
        self.base.set_value(value);
    }

    /// Resets all statistics.
    pub fn reset_statistics(&mut self) {
        self.buffer_x.reset();
        self.buffer_y.reset();
        self.sum_x = 0.0;
        self.sum_y = 0.0;
        self.sum_xx = 0.0;
        self.sum_yy = 0.0;
        self.sum_xy = 0.0;
    }
}

/// Macro to implement common PairRollingOperator methods.
#[macro_export]
macro_rules! impl_pair_rolling_operator_common {
    ($type:ty) => {
        impl PairRollingOperator for $type {
            #[inline]
            fn name(&self) -> &str {
                &self.base.base.name
            }

            #[inline]
            fn window_size(&self) -> usize {
                self.base.base.buffer.window_size()
            }

            #[inline]
            fn is_ready(&self) -> bool {
                self.base.base.valid_count >= self.base.base.buffer.window_size()
            }

            #[inline]
            fn value(&self) -> f64 {
                if self.is_ready() {
                    self.base.base.value
                } else {
                    f64::NAN
                }
            }

            #[inline]
            fn update(&mut self, value1: f64, value2: f64) {
                self.update_internal(value1, value2);
            }

            #[inline]
            fn count(&self) -> usize {
                self.base.buffer_x.count()
            }

            fn reset(&mut self) {
                self.base.reset_statistics();
                self.base.base.value = f64::NAN;
                self.base.base.valid_count = 0;
                self.base.base.last_valid_value = None;
            }
        }
    };
}

/// Rolling correlation operator with O(1) updates.
#[derive(Debug)]
pub struct Correlation {
    base: PairBaseOperator,
}

impl Correlation {
    /// Creates a new rolling correlation operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: PairBaseOperator::new("TS_Corr", window_size),
        }
    }
}

impl_pair_rolling_operator_common!(Correlation);

impl Correlation {
    /// Updates the operator with new values and calculates correlation.
    pub fn update_internal(&mut self, x: f64, y: f64) {
        self.base.update_statistics(x, y);

        // Only compute if we have enough valid samples
        if self.base.base().valid_count() >= self.base.buffer_x().window_size() {
            let n = self.base.buffer_x().window_size() as f64;
            
            // Correlation formula: (n*ΣXY - ΣX*ΣY) / sqrt((n*ΣX² - (ΣX)²)(n*ΣY² - (ΣY)²))
            let numerator = n * self.base.sum_xy() - self.base.sum_x() * self.base.sum_y();
            let denominator_x = n * self.base.sum_xx() - self.base.sum_x() * self.base.sum_x();
            let denominator_y = n * self.base.sum_yy() - self.base.sum_y() * self.base.sum_y();
            
            let denominator = (denominator_x * denominator_y).sqrt();
            
            if denominator > f64::EPSILON {
                let correlation = numerator / denominator;
                self.base.set_value(correlation.clamp(-1.0, 1.0)); // Clamp to valid correlation range
            } else {
                // No variation in one or both series
                self.base.set_value(f64::NAN);
            }
        }
    }
}

/// Rolling covariance operator with O(1) updates.
#[derive(Debug)]
pub struct Covariance {
    base: PairBaseOperator,
    ddof: usize,
}

impl Covariance {
    /// Creates a new rolling covariance operator.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: PairBaseOperator::new("TS_Cov", window_size),
            ddof,
        }
    }
}

impl_pair_rolling_operator_common!(Covariance);

impl Covariance {
    /// Updates the operator with new values and calculates covariance.
    pub fn update_internal(&mut self, x: f64, y: f64) {
        self.base.update_statistics(x, y);

        // Only compute if we have enough valid samples
        if self.base.base().valid_count() >= self.base.buffer_x().window_size() {
            let n = self.base.buffer_x().window_size() as f64;
            
            // Sample covariance: (ΣXY - ΣX*ΣY/n) / (n-ddof)
            let mean_x = self.base.sum_x() / n;
            let mean_y = self.base.sum_y() / n;
            let mean_xy = self.base.sum_xy() / n;
            
            let covariance = (mean_xy - mean_x * mean_y) * n / (n - self.ddof as f64);
            
            self.base.set_value(covariance);
        }
    }
}

/// Rolling beta coefficient operator with O(1) updates.
#[derive(Debug)]
pub struct Beta {
    base: PairBaseOperator,
    ddof: usize,
}

impl Beta {
    /// Creates a new rolling beta operator.
    /// Beta = Cov(X,Y) / Var(Y) where X is dependent, Y is independent variable.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: PairBaseOperator::new("TS_Beta", window_size),
            ddof,
        }
    }
}

impl_pair_rolling_operator_common!(Beta);

impl Beta {
    /// Updates the operator with new values and calculates beta.
    pub fn update_internal(&mut self, x: f64, y: f64) {
        self.base.update_statistics(x, y);

        // Only compute if we have enough valid samples
        if self.base.base().valid_count() >= self.base.buffer_x().window_size() {
            let n = self.base.buffer_x().window_size() as f64;
            
            // Calculate covariance and variance of Y
            let mean_x = self.base.sum_x() / n;
            let mean_y = self.base.sum_y() / n;
            let mean_xy = self.base.sum_xy() / n;
            let mean_yy = self.base.sum_yy() / n;
            
            // Covariance(X,Y)
            let covariance = (mean_xy - mean_x * mean_y) * n / (n - self.ddof as f64);
            
            // Variance(Y)
            let variance_y = (mean_yy - mean_y * mean_y) * n / (n - self.ddof as f64);
            
            if variance_y > f64::EPSILON {
                let beta = covariance / variance_y;
                self.base.set_value(beta);
            } else {
                // No variation in Y (independent variable)
                self.base.set_value(f64::NAN);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_correlation_operator() {
        let mut op = Correlation::new(3);
        
        assert!(!op.is_ready());
        assert!(op.value().is_nan());
        
        // Perfect positive correlation
        op.update(1.0, 1.0);
        op.update(2.0, 2.0);
        op.update(3.0, 3.0);
        
        assert!(op.is_ready());
        assert!((op.value() - 1.0).abs() < f64::EPSILON);
        
        // Add another point maintaining perfect correlation
        op.update(4.0, 4.0);
        assert!((op.value() - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_covariance_operator() {
        let mut op = Covariance::new(3, 1);
        
        assert!(!op.is_ready());
        assert!(op.value().is_nan());
        
        op.update(1.0, 1.0);
        op.update(2.0, 2.0);
        op.update(3.0, 3.0);
        
        assert!(op.is_ready());
        assert!(op.value() > 0.0); // Positive covariance
    }

    #[test]
    fn test_beta_operator() {
        let mut op = Beta::new(3, 1);
        
        assert!(!op.is_ready());
        assert!(op.value().is_nan());
        
        // Beta = 1 case (X = Y)
        op.update(1.0, 1.0);
        op.update(2.0, 2.0);
        op.update(3.0, 3.0);
        
        assert!(op.is_ready());
        assert!((op.value() - 1.0).abs() < 0.1); // Should be close to 1.0
    }

    #[test]
    fn test_nan_handling() {
        let mut op = Correlation::new(3);
        
        // NaN inputs should be skipped
        op.update(1.0, f64::NAN);
        op.update(f64::NAN, 2.0);
        op.update(2.0, 2.0);
        op.update(3.0, 3.0);
        op.update(4.0, 4.0);
        
        assert!(op.is_ready());
        assert!((op.value() - 1.0).abs() < f64::EPSILON);
    }
}