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

use crate::{buffer::RollingBuffer, operators::BaseOperator};
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
    // Joint validity tracking (torch-style semantics)
    valid_pairs: usize,
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
            valid_pairs: 0,
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

    /// Returns the number of jointly-valid pairs in the current window.
    #[inline]
    pub fn valid_pairs(&self) -> usize {
        self.valid_pairs
    }

    /// Updates running statistics with new values (O(1) operation).
    pub fn update_statistics(&mut self, x: f64, y: f64) {
        // Always advance both buffers, even for NaN
        let evicted_x = self.buffer_x.update(x);
        let evicted_y = self.buffer_y.update(y);

        // Track validity of input and evicted values (joint validity)
        let input_valid = !x.is_nan() && !y.is_nan();
        let evicted_valid = evicted_x.map_or(false, |v| !v.is_nan())
            && evicted_y.map_or(false, |v| !v.is_nan());

        // Subtract evicted valid pair from running sums and decrement valid_pairs
        if evicted_valid {
            if let (Some(old_x), Some(old_y)) = (evicted_x, evicted_y) {
                self.sum_x -= old_x;
                self.sum_y -= old_y;
                self.sum_xx -= old_x * old_x;
                self.sum_yy -= old_y * old_y;
                self.sum_xy -= old_x * old_y;

                // Decrement joint valid pairs counter
                self.valid_pairs = self.valid_pairs.saturating_sub(1);
            }
        }

        // Add new valid pair to running sums and increment valid_pairs
        if input_valid {
            self.sum_x += x;
            self.sum_y += y;
            self.sum_xx += x * x;
            self.sum_yy += y * y;
            self.sum_xy += x * y;

            // Increment joint valid pairs counter
            self.valid_pairs += 1;
        }

        // Debug assertion: valid_pairs should never exceed the minimum of individual valid counts
        debug_assert!(
            self.valid_pairs <= self.buffer_x.valid_len().min(self.buffer_y.valid_len()),
            "valid_pairs ({}) exceeds min(valid_x={}, valid_y={})",
            self.valid_pairs,
            self.buffer_x.valid_len(),
            self.buffer_y.valid_len()
        );
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
        self.valid_pairs = 0;
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
                self.base.buffer_x.count() >= self.base.buffer_x.window_size()
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

        // Check if we have any jointly-valid pairs in the current window
        if self.base.valid_pairs() == 0 {
            // No valid pairs, reuse last valid correlation
            self.base.base.set_stale_value();
            return;
        }

        let n = self.base.valid_pairs() as f64;

        // Correlation formula: (n*ΣXY - ΣX*ΣY) / sqrt((n*ΣX² - (ΣX)²)(n*ΣY² - (ΣY)²))
        let numerator = n * self.base.sum_xy() - self.base.sum_x() * self.base.sum_y();
        let denominator_x = n * self.base.sum_xx() - self.base.sum_x() * self.base.sum_x();
        let denominator_y = n * self.base.sum_yy() - self.base.sum_y() * self.base.sum_y();

        let denominator = (denominator_x * denominator_y).sqrt();

        if denominator > f64::EPSILON {
            let correlation = numerator / denominator;
            self.base.set_value(correlation.clamp(-1.0, 1.0)); // Clamp to valid correlation range
        } else {
            // No variation in one or both series, reuse last valid
            self.base.base.set_stale_value();
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

        // Check if we have enough jointly-valid pairs for ddof
        if self.base.valid_pairs() == 0 || self.base.valid_pairs() <= self.ddof {
            // No valid pairs or insufficient for ddof, reuse last valid covariance
            self.base.base.set_stale_value();
            return;
        }

        let n = self.base.valid_pairs() as f64;

        // Sample covariance: (ΣXY - ΣX*ΣY/n) / (n-ddof)
        let mean_x = self.base.sum_x() / n;
        let mean_y = self.base.sum_y() / n;
        let mean_xy = self.base.sum_xy() / n;

        let covariance = (mean_xy - mean_x * mean_y) * n / (n - self.ddof as f64);

        self.base.set_value(covariance);
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

        // Check if we have enough jointly-valid pairs for ddof
        if self.base.valid_pairs() == 0 || self.base.valid_pairs() <= self.ddof {
            // No valid pairs or insufficient for ddof, reuse last valid beta
            self.base.base.set_stale_value();
            return;
        }

        let n = self.base.valid_pairs() as f64;

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
            // No variation in Y (independent variable), reuse last valid
            self.base.base.set_stale_value();
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

    #[test]
    fn test_correlation_nan_misalignment() {
        let mut op = Correlation::new(5);

        // Alternating NaN scenario - tests joint-validity tracking
        // Only pairs where both are valid should be counted
        op.update(1.0, f64::NAN);      // pair 0: invalid (y is NaN)
        op.update(f64::NAN, 2.0);      // pair 1: invalid (x is NaN)
        op.update(3.0, 3.0);           // pair 2: valid
        op.update(4.0, 4.0);           // pair 3: valid
        op.update(5.0, 5.0);           // pair 4: valid

        assert!(op.is_ready());
        // Only 3 valid pairs: (3,3), (4,4), (5,5) - perfect correlation
        assert!((op.value() - 1.0).abs() < 1e-9, "Expected perfect correlation for valid pairs");

        // Add more data to test rolling behavior
        op.update(6.0, 6.0);           // pair 5: valid, evicts pair 0 (was invalid)
        assert!((op.value() - 1.0).abs() < 1e-9);

        // Now add a misaligned pair
        op.update(f64::NAN, 7.0);      // pair 6: invalid, evicts pair 1 (was invalid)
        // Window: [pair 2,3,4,5,6] -> valid pairs: [pair 2,3,4,5] = 4 pairs
        assert!((op.value() - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_correlation_zero_valid_pairs() {
        let mut op = Correlation::new(3);

        // No jointly-valid pairs - all are misaligned NaN
        op.update(1.0, f64::NAN);
        op.update(f64::NAN, 2.0);
        op.update(3.0, f64::NAN);

        assert!(op.is_ready()); // Window is full (3 updates)
        // But no valid pairs, so should return NaN (no previous valid value)
        assert!(op.value().is_nan(), "Expected NaN when no valid pairs exist");

        // Add one valid pair
        op.update(4.0, 4.0);
        // Window now: [NaN,2.0], [3.0,NaN], [4.0,4.0] -> only 1 valid pair
        // Cannot compute correlation with only 1 pair, should reuse stale (NaN)
        assert!(op.value().is_nan(), "Expected NaN with only 1 valid pair");

        // Add another valid pair
        op.update(5.0, 5.0);
        // Window: [3.0,NaN], [4.0,4.0], [5.0,5.0] -> 2 valid pairs
        // Can now compute correlation
        assert!(!op.value().is_nan(), "Expected valid correlation with 2+ pairs");
    }

    #[test]
    fn test_covariance_joint_validity() {
        let mut op = Covariance::new(5, 1);

        // Mix of valid and invalid pairs
        op.update(f64::NAN, 1.0);      // invalid
        op.update(2.0, f64::NAN);      // invalid
        op.update(3.0, 3.0);           // valid
        op.update(4.0, 4.0);           // valid
        op.update(5.0, 5.0);           // valid

        assert!(op.is_ready());
        // Should compute covariance using only 3 valid pairs
        // Cov([3,4,5], [3,4,5]) = Var([3,4,5]) = 1.0 (with ddof=1)
        assert!((op.value() - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_beta_joint_validity() {
        let mut op = Beta::new(5, 1);

        // Scenario: some NaN pairs
        op.update(f64::NAN, 2.0);      // invalid
        op.update(3.0, f64::NAN);      // invalid
        op.update(4.0, 2.0);           // valid: x=4, y=2
        op.update(5.0, 2.5);           // valid: x=5, y=2.5
        op.update(6.0, 3.0);           // valid: x=6, y=3.0

        assert!(op.is_ready());
        // Beta with 3 valid pairs: (4,2), (5,2.5), (6,3)
        // X increases with Y, so beta should be positive
        assert!(op.value() > 0.0, "Expected positive beta");
        assert!(op.value().is_finite(), "Expected finite beta value");
    }

    #[test]
    fn test_pair_operator_valid_pairs_counter() {
        let mut op = Correlation::new(3);

        // Manually test the valid_pairs counter through the public interface
        op.update(1.0, 1.0);
        assert_eq!(op.count(), 1); // Total updates
        // We can't directly access valid_pairs from here, but we can verify behavior

        op.update(f64::NAN, 2.0);
        assert_eq!(op.count(), 2);

        op.update(3.0, f64::NAN);
        assert_eq!(op.count(), 3);
        assert!(op.is_ready());

        // Only 1 valid pair so far: (1.0, 1.0)
        // Cannot compute correlation with just 1 pair
        assert!(op.value().is_nan());

        // Add more valid pairs
        op.update(4.0, 4.0); // evicts (1.0, 1.0), window: [NaN,2], [3,NaN], [4,4]
        assert_eq!(op.count(), 4);
        // Still only 1 valid pair

        op.update(5.0, 5.0); // evicts [NaN,2], window: [3,NaN], [4,4], [5,5]
        // Now 2 valid pairs: (4,4), (5,5)
        assert!(!op.value().is_nan(), "Should compute correlation with 2+ valid pairs");
        assert!((op.value() - 1.0).abs() < f64::EPSILON);
    }
}
