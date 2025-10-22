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

    #[test]
    fn test_mean_selq_basic_functionality() {
        let mut op = MeanSelQ::new(5, 0.25, 0.75);

        assert!(!op.is_ready());
        assert!(op.value().is_nan());

        // Add data: x values are 10-50, cond values are 1-5
        // After window is full, cond=[1,2,3,4,5]
        // Q1(cond)=2.0, Q3(cond)=4.0
        // x values where cond in [2.0, 4.0]: x=[20, 30, 40]
        // Mean of [20, 30, 40] = 30.0
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);
        op.update(40.0, 4.0);
        op.update(50.0, 5.0);

        assert!(op.is_ready());
        let result = op.value();
        assert!((result - 30.0).abs() < 0.1, "Expected mean ~30.0, got {}", result);
    }

    #[test]
    fn test_mean_selq_extreme_quantiles() {
        let mut op = MeanSelQ::new(5, 0.0, 1.0);

        // With quantiles [0.0, 1.0], all values should be selected
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);
        op.update(40.0, 4.0);
        op.update(50.0, 5.0);

        assert!(op.is_ready());
        let result = op.value();
        // Mean of all x values [10, 20, 30, 40, 50] = 30.0
        assert!((result - 30.0).abs() < 0.1);
    }

    #[test]
    fn test_mean_selq_single_quantile() {
        let mut op = MeanSelQ::new(5, 0.5, 0.5);

        // With quantiles [0.5, 0.5], only median of cond should be selected
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);
        op.update(40.0, 4.0);
        op.update(50.0, 5.0);

        assert!(op.is_ready());
        // Median of cond=[1,2,3,4,5] is 3.0
        // Only x=30.0 should be selected
        let result = op.value();
        assert!((result - 30.0).abs() < 0.1);
    }

    #[test]
    fn test_mean_selq_nan_handling() {
        let mut op = MeanSelQ::new(5, 0.25, 0.75);

        // Add data with NaN in cond
        op.update(10.0, 1.0);
        op.update(20.0, f64::NAN); // This pair should be excluded
        op.update(30.0, 3.0);
        op.update(40.0, 4.0);
        op.update(50.0, 5.0);

        assert!(op.is_ready());
        // Valid cond values: [1, 3, 4, 5]
        // Q1=2.5, Q3=4.5
        // x values where cond in [2.5, 4.5]: x=[30, 40]
        // Mean = 35.0
        let result = op.value();
        assert!(
            (result - 35.0).abs() < 0.1,
            "Expected mean ~35.0 with NaN filtering, got {}",
            result
        );
    }

    #[test]
    fn test_mean_selq_empty_selection() {
        let mut op = MeanSelQ::new(3, 0.9, 1.0);

        // First, establish a valid value
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);

        assert!(op.is_ready());
        let first_value = op.value();
        assert!(!first_value.is_nan(), "Should have a valid value initially");

        // Now add data where selection might be empty
        // If cond=[1,2,3], Q90=2.8, Q100=3.0
        // Only x where cond in [2.8, 3.0] would be selected
        // This should select x=30.0 (cond=3.0)
        op.update(40.0, 1.0);
        assert!(!op.value().is_nan(), "Should maintain valid value");
    }

    #[test]
    fn test_mean_selq_order_invariance() {
        // MeanSelQ should NOT be order-dependent (unlike incorrect DSL workaround)
        // Window-wide quantiles should give consistent results

        let mut op1 = MeanSelQ::new(5, 0.25, 0.75);
        let mut op2 = MeanSelQ::new(5, 0.25, 0.75);

        // Same data, different order
        let data1 = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0), (40.0, 4.0), (50.0, 5.0)];
        let data2 = [(50.0, 5.0), (10.0, 1.0), (30.0, 3.0), (40.0, 4.0), (20.0, 2.0)];

        for (x, cond) in data1 {
            op1.update(x, cond);
        }

        for (x, cond) in data2 {
            op2.update(x, cond);
        }

        assert!(op1.is_ready());
        assert!(op2.is_ready());

        // After both windows are full, they should have the same set of values
        // and thus the same quantiles and same selected mean (order-invariant)
        let result1 = op1.value();
        let result2 = op2.value();

        assert!(
            (result1 - result2).abs() < 0.1,
            "Results should be order-invariant: {} vs {}",
            result1,
            result2
        );
    }

    #[test]
    fn test_mean_selq_rolling_behavior() {
        let mut op = MeanSelQ::new(3, 0.25, 0.75);

        // Initial window: [(10, 1), (20, 2), (30, 3)]
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);

        assert!(op.is_ready());
        let first_result = op.value();

        // Add more data to test rolling behavior
        // Window becomes: [(20, 2), (30, 3), (40, 4)]
        op.update(40.0, 4.0);

        let second_result = op.value();

        // Results should differ as window content changed
        assert!(
            (first_result - second_result).abs() > 0.01,
            "Rolling window should produce different results"
        );
    }

    #[test]
    fn test_mean_selq_all_nan_cond() {
        let mut op = MeanSelQ::new(3, 0.25, 0.75);

        // Establish a valid value first
        op.update(10.0, 1.0);
        op.update(20.0, 2.0);
        op.update(30.0, 3.0);

        assert!(op.is_ready());

        // Now add data that will roll the window
        // After (40, NaN), window = [(20, 2), (30, 3), (40, NaN)], valid_cond=[2,3]
        op.update(40.0, f64::NAN);
        // After (50, NaN), window = [(30, 3), (40, NaN), (50, NaN)], valid_cond=[3]
        op.update(50.0, f64::NAN);
        assert!(op.is_ready());
        let last_valid = op.value(); // This should be 30.0 (only x=30 with cond=3)

        // After (60, NaN), window = [(40, NaN), (50, NaN), (60, NaN)], valid_cond=[]
        op.update(60.0, f64::NAN);

        // Following consistent NaN strategy with other pair rolling operators:
        // is_ready() should return true (window is full)
        // value() should reuse last valid value when window has no valid data
        assert!(op.is_ready(), "Should be ready when window is full (count >= window_size)");

        let result = op.value();
        assert_eq!(
            result, last_valid,
            "Should reuse last valid value when all cond are NaN, expected {}, got {}",
            last_valid, result
        );
    }

    #[test]
    fn test_mean_selq_parameter_validation() {
        // Test that low_phi > high_phi panics
        let result = std::panic::catch_unwind(|| {
            MeanSelQ::new(5, 0.75, 0.25); // Invalid: low > high
        });
        assert!(result.is_err(), "Should panic when low_phi > high_phi");

        // Test that phi outside [0, 1] panics
        let result = std::panic::catch_unwind(|| {
            MeanSelQ::new(5, -0.1, 0.5); // Invalid: low_phi < 0
        });
        assert!(result.is_err(), "Should panic when low_phi < 0");

        let result = std::panic::catch_unwind(|| {
            MeanSelQ::new(5, 0.5, 1.1); // Invalid: high_phi > 1
        });
        assert!(result.is_err(), "Should panic when high_phi > 1");
    }
}

/// Rolling mean with quantile-based selection.
///
/// Computes the NaN-aware mean of target values (x) where the corresponding
/// selector values (cond) fall within a specified quantile range [low, high].
///
/// # Algorithm
/// At each time step:
/// 1. Compute quantile thresholds q_low and q_high from the current window of cond values
/// 2. Filter x values where corresponding cond is in [q_low, q_high] and both are non-NaN
/// 3. Return the mean of filtered x values
///
/// # Performance
/// Uses two Quantile operators to efficiently maintain low and high quantile thresholds
/// with O(log n) updates instead of O(n log n) sorting on every update.
///
/// # NaN Handling
/// - When cond is NaN, the corresponding x is excluded from selection
/// - When the selection is empty, reuse the last valid mean value
#[derive(Debug)]
pub struct MeanSelQ {
    base: PairBaseOperator,
    quantile_low: crate::operators::rolling::Quantile,  // Maintains q_low efficiently
    quantile_high: crate::operators::rolling::Quantile, // Maintains q_high efficiently
}

impl MeanSelQ {
    /// Creates a new rolling mean with quantile-based selection operator.
    ///
    /// # Arguments
    /// * `window_size` - Size of the rolling window
    /// * `low_phi` - Low quantile threshold (0.0-1.0)
    /// * `high_phi` - High quantile threshold (0.0-1.0)
    ///
    /// # Panics
    /// Panics if low_phi > high_phi or if either is outside [0, 1].
    #[must_use]
    pub fn new(window_size: usize, low_phi: f64, high_phi: f64) -> Self {
        assert!(
            low_phi >= 0.0 && low_phi <= 1.0,
            "low_phi must be in [0, 1], got {}",
            low_phi
        );
        assert!(
            high_phi >= 0.0 && high_phi <= 1.0,
            "high_phi must be in [0, 1], got {}",
            high_phi
        );
        assert!(
            low_phi <= high_phi,
            "low_phi ({}) must be <= high_phi ({})",
            low_phi,
            high_phi
        );

        Self {
            base: PairBaseOperator::new("TS_MeanSelQ", window_size),
            quantile_low: crate::operators::rolling::Quantile::new(window_size, low_phi),
            quantile_high: crate::operators::rolling::Quantile::new(window_size, high_phi),
        }
    }
}

// Manual implementation for MeanSelQ to override reset()
impl PairRollingOperator for MeanSelQ {
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
        // Following consistent NaN strategy: ready when count >= window_size
        // (same as other pair rolling operators)
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

        // Also reset the quantile operators
        use crate::operators::RollingOperator;
        self.quantile_low.reset();
        self.quantile_high.reset();
    }
}

impl MeanSelQ {
    /// Updates the operator with new values and calculates the conditional mean.
    pub fn update_internal(&mut self, x: f64, cond: f64) {
        // Always update both buffers to maintain time alignment
        self.base.update_statistics(x, cond);

        // Update quantile operators with cond value (O(log n) operation)
        use crate::operators::RollingOperator;
        self.quantile_low.update(cond);
        self.quantile_high.update(cond);

        // Check if we have any jointly-valid pairs in the current window
        if self.base.valid_pairs() == 0 {
            // No valid pairs, reuse last valid mean
            self.base.base.set_stale_value();
            return;
        }

        // Get quantile thresholds from pre-computed quantile operators
        let q_low = self.quantile_low.value();
        let q_high = self.quantile_high.value();

        if q_low.is_nan() || q_high.is_nan() {
            // Cannot compute quantiles, reuse last valid mean
            self.base.base.set_stale_value();
            return;
        }

        // Extract windows for filtering
        let x_window = self.base.buffer_x().window();
        let cond_window = self.base.buffer_y().window();

        // Filter x values where corresponding cond is in [q_low, q_high]
        // Both x and cond must be non-NaN, and cond must be within the quantile range
        let mut sum = 0.0;
        let mut count = 0;

        for i in 0..x_window.len() {
            let xi = x_window[i];
            let ci = cond_window[i];

            if !xi.is_nan() && !ci.is_nan() && ci >= q_low && ci <= q_high {
                sum += xi;
                count += 1;
            }
        }

        if count == 0 {
            // No values passed the selection criteria, reuse last valid mean
            self.base.base.set_stale_value();
        } else {
            // Compute mean of selected values
            let mean = sum / count as f64;
            self.base.set_value(mean);
        }
    }
}
