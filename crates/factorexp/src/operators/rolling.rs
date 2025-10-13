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

//! Basic rolling statistical operators.

use crate::{
    impl_rolling_operator_common,
    operators::{BaseOperator, RollingOperator},
};

/// Rolling mean (average) operator.
#[derive(Debug)]
pub struct Mean {
    base: BaseOperator,
}

impl Mean {
    /// Creates a new rolling mean operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Mean", window_size),
        }
    }
}

impl_rolling_operator_common!(Mean);

impl Mean {
    /// Updates the operator with a new value and recalculates the mean.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid mean
            self.base.set_stale_value();
            return;
        }

        // Compute mean from valid values (buffer.mean() is now NaN-aware)
        self.base.set_value(self.base.buffer().mean());
    }
}

/// Rolling sum operator.
#[derive(Debug)]
pub struct Sum {
    base: BaseOperator,
}

impl Sum {
    /// Creates a new rolling sum operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Sum", window_size),
        }
    }
}

impl_rolling_operator_common!(Sum);

impl Sum {
    /// Updates the operator with a new value and recalculates the sum.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid sum
            self.base.set_stale_value();
            return;
        }

        // Compute sum from valid values (buffer.valid_sum() is NaN-aware)
        self.base.set_value(self.base.buffer().valid_sum());
    }
}

/// Rolling standard deviation operator.
#[derive(Debug)]
pub struct Std {
    base: BaseOperator,
    ddof: usize,
}

impl Std {
    /// Creates a new rolling standard deviation operator.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Std", window_size),
            ddof,
        }
    }
}

impl_rolling_operator_common!(Std);

impl Std {
    /// Updates the operator with a new value and recalculates the standard deviation.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid std
            self.base.set_stale_value();
            return;
        }

        // Compute std from valid values (buffer.std() is NaN-aware)
        self.base.set_value(self.base.buffer().std(self.ddof));
    }
}

/// Rolling variance operator.
#[derive(Debug)]
pub struct Var {
    base: BaseOperator,
    ddof: usize,
}

impl Var {
    /// Creates a new rolling variance operator.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Var", window_size),
            ddof,
        }
    }
}

impl_rolling_operator_common!(Var);

impl Var {
    /// Updates the operator with a new value and recalculates the variance.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid variance
            self.base.set_stale_value();
            return;
        }

        // Compute variance from valid values (buffer.variance() is NaN-aware)
        self.base.set_value(self.base.buffer().variance(self.ddof));
    }
}

/// Rolling minimum operator.
#[derive(Debug)]
pub struct Min {
    base: BaseOperator,
}

impl Min {
    /// Creates a new rolling minimum operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Min", window_size),
        }
    }
}

impl_rolling_operator_common!(Min);

impl Min {
    /// Updates the operator with a new value and recalculates the minimum.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid min
            self.base.set_stale_value();
            return;
        }

        // Compute min from valid values (buffer.min() filters NaN)
        if let Some(min) = self.base.buffer().min() {
            self.base.set_value(min);
        }
    }
}

/// Rolling maximum operator.
#[derive(Debug)]
pub struct Max {
    base: BaseOperator,
}

impl Max {
    /// Creates a new rolling maximum operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Max", window_size),
        }
    }
}

impl_rolling_operator_common!(Max);

impl Max {
    /// Updates the operator with a new value and recalculates the maximum.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid max
            self.base.set_stale_value();
            return;
        }

        // Compute max from valid values (buffer.max() filters NaN)
        if let Some(max) = self.base.buffer().max() {
            self.base.set_value(max);
        }
    }
}

/// Rolling median operator.
#[derive(Debug)]
pub struct Median {
    base: BaseOperator,
}

impl Median {
    /// Creates a new rolling median operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Med", window_size),
        }
    }
}

impl_rolling_operator_common!(Median);

impl Median {
    /// Updates the operator with a new value and recalculates the median.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid median
            self.base.set_stale_value();
            return;
        }

        // Compute median from valid values (filter NaN from window)
        let mut sorted: Vec<f64> = self.base.buffer().values_valid();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let mid = sorted.len() / 2;

        let median = if sorted.len() % 2 == 0 {
            (sorted[mid - 1] + sorted[mid]) / 2.0
        } else {
            sorted[mid]
        };

        self.base.set_value(median);
    }
}

/// Rolling delta (difference) operator.
/// Computes the difference between current value and value from n periods ago.
#[derive(Debug)]
pub struct Delta {
    base: BaseOperator,
    period: usize,
}

impl Delta {
    /// Creates a new rolling delta operator.
    /// The window_size should be at least period + 1 to hold enough values.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        // Default period is 1 (difference from previous value)
        let period = window_size.saturating_sub(1).max(1);
        Self {
            base: BaseOperator::new("TS_Delta", window_size.max(2)),
            period,
        }
    }

    /// Creates a new rolling delta operator with explicit period.
    #[must_use]
    pub fn with_period(window_size: usize, period: usize) -> Self {
        let period = period.max(1);
        Self {
            base: BaseOperator::new("TS_Delta", window_size.max(period + 1)),
            period,
        }
    }
}

impl_rolling_operator_common!(Delta);

impl Delta {
    /// Updates the operator with a new value and calculates the delta (difference).
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Need enough data in the buffer
        let len = self.base.buffer().len();
        if len <= self.period {
            // Not enough data yet
            return;
        }

        // Get current value and value from 'period' bars ago
        if let (Some(old_value), Some(current)) = (
            self.base.buffer().get(len - self.period - 1),
            self.base.buffer().get(len - 1),
        ) {
            // Check if both values are valid (non-NaN)
            if !old_value.is_nan() && !current.is_nan() {
                self.base.set_value(current - old_value);
            } else {
                // One or both values are NaN, reuse last valid delta
                self.base.set_stale_value();
            }
        } else {
            // Failed to get values, reuse last
            self.base.set_stale_value();
        }
    }
}

/// Rolling reference operator (value from N periods ago).
#[derive(Debug)]
pub struct Ref {
    base: BaseOperator,
    period: usize,
}

impl Ref {
    /// Creates a new rolling reference operator.
    #[must_use]
    pub fn new(window_size: usize, period: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Ref", window_size),
            period,
        }
    }
}

impl_rolling_operator_common!(Ref);

impl Ref {
    /// Updates the operator with a new value and gets reference value.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Need enough data in the buffer
        let len = self.base.buffer().len();
        if len <= self.period {
            // Not enough data yet
            return;
        }

        // Get value from N periods ago (counting from current position)
        // For period=1: current is at len-1, 1 period ago is at len-1-1 = len-2
        let ref_index = len - 1 - self.period;
        if let Some(ref_value) = self.base.buffer().get(ref_index) {
            // Check if the reference value is valid (non-NaN)
            if !ref_value.is_nan() {
                self.base.set_value(ref_value);
            } else {
                // Reference value is NaN, reuse last valid ref
                self.base.set_stale_value();
            }
        } else {
            // Failed to get value, reuse last
            self.base.set_stale_value();
        }
    }
}

/// Rolling rank operator (rank of current value within window).
#[derive(Debug)]
pub struct Rank {
    base: BaseOperator,
}

impl Rank {
    /// Creates a new rolling rank operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Rank", window_size),
        }
    }
}

impl_rolling_operator_common!(Rank);

impl Rank {
    /// Updates the operator with a new value and calculates rank.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid rank
            self.base.set_stale_value();
            return;
        }

        // Find the latest valid value by scanning backward from the end
        let all_values = self.base.buffer().window();
        let current_value = all_values
            .iter()
            .rev()
            .find(|&&x| !x.is_nan())
            .copied();

        if let Some(current) = current_value {
            // Compute rank using only valid values
            let valid_values = self.base.buffer().values_valid();

            // Count how many values are less than current value
            let smaller_count = valid_values.iter().filter(|&&x| x < current).count() as f64;

            // Normalize rank to [0, 1] range
            // 0 = smallest value, 1 = largest value
            let rank = if valid_values.len() <= 1 {
                0.0
            } else {
                smaller_count / (valid_values.len() - 1) as f64
            };

            self.base.set_value(rank);
        } else {
            // No valid value found, reuse last
            self.base.set_stale_value();
        }
    }
}

/// Rolling argmax operator (index of maximum value in window).
#[derive(Debug)]
pub struct Argmax {
    base: BaseOperator,
}

impl Argmax {
    /// Creates a new rolling argmax operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Argmax", window_size),
        }
    }
}

impl_rolling_operator_common!(Argmax);

impl Argmax {
    /// Updates the operator with a new value and finds argmax.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid argmax
            self.base.set_stale_value();
            return;
        }

        // Find argmax among valid values (filter NaN)
        let values = self.base.buffer().window();

        if let Some((argmax_idx, _)) = values
            .iter()
            .enumerate()
            .filter(|(_, v)| !v.is_nan())
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
        {
            self.base.set_value(argmax_idx as f64);
        } else {
            // No valid values found, reuse last
            self.base.set_stale_value();
        }
    }
}

/// Rolling argmin operator (index of minimum value in window).
#[derive(Debug)]
pub struct Argmin {
    base: BaseOperator,
}

impl Argmin {
    /// Creates a new rolling argmin operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Argmin", window_size),
        }
    }
}

impl_rolling_operator_common!(Argmin);

impl Argmin {
    /// Updates the operator with a new value and finds argmin.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid argmin
            self.base.set_stale_value();
            return;
        }

        // Find argmin among valid values (filter NaN)
        let values = self.base.buffer().window();

        if let Some((argmin_idx, _)) = values
            .iter()
            .enumerate()
            .filter(|(_, v)| !v.is_nan())
            .min_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
        {
            self.base.set_value(argmin_idx as f64);
        } else {
            // No valid values found, reuse last
            self.base.set_stale_value();
        }
    }
}

/// Rolling product operator.
#[derive(Debug)]
pub struct Product {
    base: BaseOperator,
}

impl Product {
    /// Creates a new rolling product operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Product", window_size),
        }
    }
}

impl_rolling_operator_common!(Product);

impl Product {
    /// Updates the operator with a new value and calculates product.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid product
            self.base.set_stale_value();
            return;
        }

        // Compute product from valid values (filter NaN)
        let product = self
            .base
            .buffer()
            .iter_valid()
            .fold(1.0, |acc, x| acc * x);
        self.base.set_value(product);
    }
}

/// Rolling ZScore operator (standardization).
/// Computes (value - mean) / std over a rolling window.
#[derive(Debug)]
pub struct ZScore {
    base: BaseOperator,
    ddof: usize,
}

impl ZScore {
    /// Creates a new rolling ZScore operator.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: BaseOperator::new("ZScore", window_size),
            ddof,
        }
    }
}

impl_rolling_operator_common!(ZScore);

impl ZScore {
    /// Updates the operator with a new value and calculates ZScore.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Get the latest valid value by scanning backward
        let all_values = self.base.buffer().window();
        let current_value = all_values
            .iter()
            .rev()
            .find(|&&x| !x.is_nan())
            .copied();

        // Check if we have any valid values and a valid current value
        if self.base.buffer().valid_len() == 0 || current_value.is_none() {
            // No valid values: reuse last valid zscore
            self.base.set_stale_value();
            return;
        }

        let current = current_value.unwrap();

        // Use buffer's NaN-aware mean and std
        let mean = self.base.buffer().mean();
        let std = self.base.buffer().std(self.ddof);

        // Check if std is valid and non-zero
        if std.is_nan() || std <= 0.0 {
            // Cannot compute zscore, reuse last valid
            self.base.set_stale_value();
        } else {
            // ZScore = (current_value - mean) / std
            let zscore = (current - mean) / std;
            self.base.set_value(zscore);
        }
    }
}

/// Rolling Demean operator.
/// Computes value - rolling_mean over a window.
#[derive(Debug)]
pub struct Demean {
    base: BaseOperator,
}

impl Demean {
    /// Creates a new rolling Demean operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("Demean", window_size),
        }
    }
}

impl_rolling_operator_common!(Demean);

impl Demean {
    /// Updates the operator with a new value and calculates demeaned value.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Get the latest valid value by scanning backward
        let all_values = self.base.buffer().window();
        let current_value = all_values
            .iter()
            .rev()
            .find(|&&x| !x.is_nan())
            .copied();

        // Check if we have any valid values and a valid current value
        if self.base.buffer().valid_len() == 0 || current_value.is_none() {
            // No valid values: reuse last valid demeaned value
            self.base.set_stale_value();
            return;
        }

        let current = current_value.unwrap();

        // Use buffer's NaN-aware mean
        let mean = self.base.buffer().mean();

        // Check if mean is valid
        if mean.is_nan() {
            // Cannot compute demean, reuse last valid
            self.base.set_stale_value();
        } else {
            // Demeaned value = current_value - mean
            let demeaned = current - mean;
            self.base.set_value(demeaned);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mean_operator() {
        let mut op = Mean::new(3);

        assert!(!op.is_ready());
        assert!(op.value().is_nan());

        op.update(1.0);
        op.update(2.0);
        op.update(3.0);

        assert!(op.is_ready());
        assert_eq!(op.value(), 2.0);

        op.update(4.0);
        assert_eq!(op.value(), 3.0);
    }

    #[test]
    fn test_std_operator() {
        let mut op = Std::new(5, 1);

        for i in 1..=5 {
            op.update(i as f64);
        }

        assert!(op.is_ready());
        let std_value = op.value();
        assert!(std_value > 1.58 && std_value < 1.59);
    }

    #[test]
    fn test_min_max_operators() {
        let mut min_op = Min::new(3);
        let mut max_op = Max::new(3);

        let values = [5.0, 2.0, 8.0, 1.0, 9.0];

        for &val in &values {
            min_op.update(val);
            max_op.update(val);
        }

        assert_eq!(min_op.value(), 1.0);
        assert_eq!(max_op.value(), 9.0);
    }

    #[test]
    fn test_zscore_operator() {
        let mut op = ZScore::new(5, 1);

        // Feed values [1, 2, 3, 4, 5]
        let values = [100.0, 102.0, 104.0, 106.0, 108.0];
        for val in values {
            op.update(val);
            print!("ZScore value after feeding {}: {}\n", val, op.value());
        }

        assert!(op.is_ready());

        // For value 5 with window [1,2,3,4,5]:
        // mean = 3, std = sqrt(2.5) ≈ 1.58
        // zscore = (5 - 3) / 1.58 ≈ 1.26
        let zscore = op.value();
        assert!(zscore > 1.25 && zscore < 1.27);

        // Test NaN handling
        op.update(f64::NAN);
        assert!(op.value() > 1.25 && op.value() < 1.27); // Should return previous valid value
    }

    #[test]
    fn test_demean_operator() {
        let mut op = Demean::new(3);

        // Feed values
        op.update(1.0);
        op.update(2.0);
        op.update(3.0);

        assert!(op.is_ready());
        // mean([1,2,3]) = 2, demean(3) = 3 - 2 = 1
        assert_eq!(op.value(), 1.0);

        op.update(4.0);
        // mean([2,3,4]) = 3, demean(4) = 4 - 3 = 1
        assert_eq!(op.value(), 1.0);

        // Test NaN handling
        op.update(f64::NAN);
        assert_eq!(op.value(), 1.0); // Should return previous valid value
    }

    #[test]
    fn test_quantile_median() {
        let mut q = Quantile::new(3, 0.5);

        // Add values 1-5
        for i in 1..=5 {
            q.update(i as f64);
        }
        assert!((q.value() - 4.0).abs() < 1e-10);

        // Rolling update: [4,5,6]
        q.update(6.0);
        assert!((q.value() - 5.0).abs() < 1e-10);
    }

    #[test]
    fn test_quantile_percentiles() {
        let mut q25 = Quantile::new(100, 0.25);
        let mut q75 = Quantile::new(100, 0.75);

        for i in 1..=100 {
            q25.update(i as f64);
            q75.update(i as f64);
        }

        // Q1 and Q3 of 1-100
        assert!((q25.value() - 25.75).abs() < 0.1);
        assert!((q75.value() - 75.25).abs() < 0.1);
    }

    #[test]
    fn test_quantile_sorted_array_impl() {
        // Test with small window to ensure sorted array is used
        let mut q = Quantile::new(10, 0.5);

        // Test with unsorted data
        let values = [5.0, 2.0, 8.0, 1.0, 9.0, 3.0, 7.0, 4.0, 6.0, 10.0];
        for val in values {
            q.update(val);
        }

        // Median of [1,2,3,4,5,6,7,8,9,10] should be 5.5
        assert!((q.value() - 5.5).abs() < 1e-10);

        // Add more values to test rolling
        q.update(11.0); // Window: [2,3,4,5,6,7,8,9,10,11]
        assert!((q.value() - 6.5).abs() < 1e-10);
    }

    #[test]
    fn test_quantile_dual_heap_impl() {
        // Test with large window to ensure dual heap is used
        let mut q = Quantile::new(2000, 0.5);

        // Fill with values
        for i in 1..=2000 {
            q.update(i as f64);
        }

        // Median should be 1000.5
        assert!((q.value() - 1000.5).abs() < 1.0);

        // Test rolling update
        q.update(2001.0); // Window: [2, 3, ..., 2001]
        println!("Quantile value after adding 2001: {}", q.value());
        assert!((q.value() - 1001.5).abs() < 1.0);
    }

    #[test]
    fn test_quantile_extreme_values() {
        let mut q_min = Quantile::new(5, 0.0); // Minimum
        let mut q_max = Quantile::new(5, 1.0); // Maximum

        let values = [3.0, 1.0, 4.0, 1.0, 5.0];
        for val in values {
            q_min.update(val);
            q_max.update(val);
        }

        assert!((q_min.value() - 1.0).abs() < 1e-10); // Min
        assert!((q_max.value() - 5.0).abs() < 1e-10); // Max
    }

    #[test]
    fn test_quantile_nan_handling() {
        let mut q = Quantile::new(1, 0.5);

        // Add some values
        q.update(1.0);
        q.update(2.0);
        q.update(3.0);
        assert!(q.is_ready());
        let valid_value = q.value();

        // NaN should be ignored
        q.update(f64::NAN);
        assert_eq!(q.value(), valid_value);

        // Inf should be handled properly
        q.update(f64::INFINITY);
        assert!(q.value().is_finite() || q.value() == f64::INFINITY);
    }

    #[test]
    fn test_quantile_duplicate_values() {
        let mut q = Quantile::new(10, 0.5);

        // Test with many duplicates
        for _ in 0..5 {
            q.update(1.0);
        }
        for _ in 0..5 {
            q.update(2.0);
        }

        // Median of [1,1,1,1,1,2,2,2,2,2] should be 1.5
        assert!((q.value() - 1.5).abs() < 1e-10);
    }

    #[test]
    fn test_quantile_single_value() {
        let mut q = Quantile::new(5, 0.5);

        q.update(41.0);
        q.update(43.0);
        q.update(44.0);
        q.update(45.0);
        q.update(46.0);
        assert!(q.is_ready());
        assert!((q.value() - 44.0).abs() < 1e-10);
    }

    #[test]
    fn test_quantile_r7_interpolation() {
        // Test R-7 interpolation method (pandas default)
        let mut q = Quantile::new(4, 0.25);

        // Values: [1, 2, 3, 4]
        for i in 1..=4 {
            q.update(i as f64);
        }

        // R-7: h = (n-1)*φ + 1 = 3*0.25 + 1 = 1.75
        // Q1 should interpolate between 1st (1.0) and 2nd (2.0) values
        // Result = 1.0 * 0.25 + 2.0 * 0.75 = 1.75
        assert!((q.value() - 1.75).abs() < 1e-10);
    }

    #[test]
    fn test_quantile_algorithm_switch() {
        // Test that algorithm switch at threshold works correctly
        let mut q_small = Quantile::new(SMALL_WINDOW_THRESHOLD, 0.5);
        let mut q_large = Quantile::new(SMALL_WINDOW_THRESHOLD + 1, 0.5);

        // Fill both with same data
        for i in 1..=SMALL_WINDOW_THRESHOLD {
            let val = i as f64;
            q_small.update(val);
            q_large.update(val);
        }

        // Add one more to large window
        q_large.update((SMALL_WINDOW_THRESHOLD + 1) as f64);

        // Both should produce valid results
        assert!(q_small.is_ready());
        assert!(q_large.is_ready());
        assert!(q_small.value().is_finite());
        assert!(q_large.value().is_finite());
    }

    #[test]
    fn test_quantile_reset_clears_state() {
        // Test with small window (SortedArray implementation)
        let mut q_small = Quantile::new(5, 0.5);

        // Fill with initial data [100, 101, 102, 103, 104]
        for i in 100..=104 {
            q_small.update(i as f64);
        }
        assert!(q_small.is_ready());
        let old_median = q_small.value();
        assert!((old_median - 102.0).abs() < 1e-10, "Expected median 102.0");

        // Reset operator
        q_small.reset();
        assert!(!q_small.is_ready(), "Should not be ready after reset");
        assert!(q_small.value().is_nan(), "Value should be NaN after reset");

        // Fill with new data [1, 2, 3, 4, 5]
        for i in 1..=5 {
            q_small.update(i as f64);
        }
        assert!(q_small.is_ready());
        let new_median = q_small.value();
        assert!(
            (new_median - 3.0).abs() < 1e-10,
            "Expected median 3.0 from new data, got {}",
            new_median
        );

        // Test with large window (DualHeap implementation)
        let mut q_large = Quantile::new(SMALL_WINDOW_THRESHOLD + 100, 0.5);

        // Fill with initial data [1000..2099]
        for i in 1000..=2099 {
            q_large.update(i as f64);
        }
        assert!(q_large.is_ready());
        let old_median_large = q_large.value();

        // Reset operator
        q_large.reset();
        assert!(!q_large.is_ready(), "Should not be ready after reset");
        assert!(q_large.value().is_nan(), "Value should be NaN after reset");

        // Fill with new data [10..1134]
        for i in 10..(10 + SMALL_WINDOW_THRESHOLD + 100) {
            q_large.update(i as f64);
        }
        assert!(q_large.is_ready());
        let new_median_large = q_large.value();

        // New median should be significantly different from old median
        assert!(
            (new_median_large - old_median_large).abs() > 500.0,
            "New median should differ from old median by at least 500"
        );
    }
}

// -------------------------------------------------------------------------------------------------
// Quantile Implementation
// -------------------------------------------------------------------------------------------------

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap, VecDeque};

/// Threshold for switching between algorithms
const SMALL_WINDOW_THRESHOLD: usize = 1024;

/// Rolling quantile operator with adaptive algorithm selection.
/// Uses sorted array for small windows (≤1024) and dual heap for larger windows.
#[derive(Debug)]
pub struct Quantile {
    base: BaseOperator,
    phi: f64, // Quantile level (0.0-1.0)
    implementation: QuantileImpl,
}

#[derive(Debug)]
enum QuantileImpl {
    SortedArray(SortedArrayQuantile),
    DualHeap(DualHeapQuantile),
}

impl Quantile {
    /// Creates a new rolling quantile operator.
    #[must_use]
    pub fn new(window_size: usize, phi: f64) -> Self {
        assert!(phi >= 0.0 && phi <= 1.0, "Quantile phi must be in [0, 1]");

        let implementation = if window_size <= SMALL_WINDOW_THRESHOLD {
            QuantileImpl::SortedArray(SortedArrayQuantile::new(window_size))
        } else {
            QuantileImpl::DualHeap(DualHeapQuantile::new(window_size, phi))
        };

        Self {
            base: BaseOperator::new("TS_Quantile", window_size),
            phi,
            implementation,
        }
    }

    /// Updates the operator with a new value.
    pub fn update_internal(&mut self, value: f64) {
        // Always advance the window (implementations handle NaN internally)
        match &mut self.implementation {
            QuantileImpl::SortedArray(inner) => {
                inner.push(value);
                if inner.is_ready() {
                    let q = inner.quantile_r7(self.phi);
                    if q.is_nan() {
                        // No valid values, reuse last valid quantile
                        self.base.set_stale_value();
                    } else {
                        self.base.set_value(q);
                    }
                } else if value.is_nan() {
                    // Not ready yet, but got NaN - reuse last
                    self.base.set_stale_value();
                }
            }
            QuantileImpl::DualHeap(inner) => {
                inner.push(value);
                if inner.is_ready() {
                    let q = inner.quantile_r7();
                    if q.is_nan() {
                        // No valid values, reuse last valid quantile
                        self.base.set_stale_value();
                    } else {
                        self.base.set_value(q);
                    }
                } else if value.is_nan() {
                    // Not ready yet, but got NaN - reuse last
                    self.base.set_stale_value();
                }
            }
        }
    }
}

// Manual implementation of RollingOperator for Quantile
// (to provide custom reset that clears internal state)
impl RollingOperator for Quantile {
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
        self.base.buffer.count() >= self.base.buffer.window_size()
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

    /// Custom reset implementation that clears internal quantile state.
    fn reset(&mut self) {
        // Reset base operator state
        self.base.buffer.reset();
        self.base.value = f64::NAN;
        self.base.last_valid_value = None;

        // Reset implementation-specific state
        match &mut self.implementation {
            QuantileImpl::SortedArray(inner) => inner.reset(),
            QuantileImpl::DualHeap(inner) => inner.reset(),
        }
    }
}

/// Sorted array implementation for small windows.
#[derive(Debug)]
struct SortedArrayQuantile {
    window_size: usize,
    time_order: VecDeque<Option<f64>>, // Maintains insertion order (None for NaN)
    sorted: Vec<f64>,                  // Maintains sorted order (valid values only)
}

impl SortedArrayQuantile {
    fn new(window_size: usize) -> Self {
        Self {
            window_size,
            time_order: VecDeque::with_capacity(window_size + 1),
            sorted: Vec::with_capacity(window_size + 1),
        }
    }

    fn push(&mut self, value: f64) {
        // Add to time order queue (None for NaN, Some for valid values)
        let opt_value = if value.is_nan() { None } else { Some(value) };
        self.time_order.push_back(opt_value);

        // Only insert valid values into sorted array
        if let Some(v) = opt_value {
            let pos = self
                .sorted
                .binary_search_by(|x| x.partial_cmp(&v).unwrap())
                .unwrap_or_else(|i| i);
            self.sorted.insert(pos, v);
        }

        // Remove oldest if window is full
        if self.time_order.len() > self.window_size {
            let old_value = self.time_order.pop_front().unwrap();

            // Only remove from sorted array if it was a valid value
            if let Some(old_val) = old_value {
                let pos = self
                    .sorted
                    .binary_search_by(|x| x.partial_cmp(&old_val).unwrap())
                    .expect("Value must exist in sorted array");
                self.sorted.remove(pos);
            }
        }
    }

    fn is_ready(&self) -> bool {
        // Ready once we have window_size updates (not just valid values)
        self.time_order.len() >= self.window_size && !self.sorted.is_empty()
    }

    /// Calculates quantile using R-7 method (pandas default).
    fn quantile_r7(&self, phi: f64) -> f64 {
        let n = self.sorted.len();
        if n == 0 {
            return f64::NAN;
        }

        if n == 1 {
            return self.sorted[0];
        }

        // R-7 method: h = (n - 1) * phi + 1 (1-based index)
        let mut h = (n as f64 - 1.0) * phi + 1.0;
        // Numerical guards to keep h within [1, n]
        if h < 1.0 {
            h = 1.0;
        } else if h > n as f64 {
            h = n as f64;
        }

        let j = h.floor();
        let g = h - j;
        let idx = (j as usize).saturating_sub(1).min(n - 1);

        if idx >= n - 1 || g <= f64::EPSILON {
            self.sorted[idx]
        } else {
            (1.0 - g) * self.sorted[idx] + g * self.sorted[idx + 1]
        }
    }

    /// Resets internal state (clears time_order and sorted arrays).
    fn reset(&mut self) {
        self.time_order.clear();
        self.sorted.clear();
    }
}

/// Dual heap implementation for medium/large windows.
#[derive(Debug)]
struct DualHeapQuantile {
    window_size: usize,
    phi: f64,
    time_order: VecDeque<Option<f64>>, // Maintains insertion order (None for NaN)
    left: BinaryHeap<OrderedFloat>,    // max-heap for lower quantiles
    right: BinaryHeap<Reverse<OrderedFloat>>, // min-heap for upper quantiles
    del_left: HashMap<u64, usize>,     // Lazy deletion counters
    del_right: HashMap<u64, usize>,
    active_count: usize, // Count of valid (non-NaN) values in current window
}

/// Wrapper for f64 to implement Ord for heap operations.
#[derive(Debug, Clone, Copy)]
struct OrderedFloat(f64);

impl PartialEq for OrderedFloat {
    fn eq(&self, other: &Self) -> bool {
        self.0.to_bits() == other.0.to_bits()
    }
}

impl Eq for OrderedFloat {}

impl PartialOrd for OrderedFloat {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        self.0.partial_cmp(&other.0)
    }
}

impl Ord for OrderedFloat {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.partial_cmp(other).unwrap()
    }
}

impl DualHeapQuantile {
    fn new(window_size: usize, phi: f64) -> Self {
        Self {
            window_size,
            phi,
            time_order: VecDeque::with_capacity(window_size + 1),
            left: BinaryHeap::new(),
            right: BinaryHeap::new(),
            del_left: HashMap::new(),
            del_right: HashMap::new(),
            active_count: 0,
        }
    }

    fn key(x: f64) -> u64 {
        x.to_bits()
    }

    fn prune_left(&mut self) {
        loop {
            let Some(&top) = self.left.peek() else { break; };
            let k = Self::key(top.0);
            let mut should_remove = false;
            let mut remove_entry = false;

            if let Some(count) = self.del_left.get_mut(&k) {
                if *count > 0 {
                    *count -= 1;
                    should_remove = true;
                    if *count == 0 {
                        remove_entry = true;
                    }
                } else {
                    break;
                }
            } else {
                break;
            }

            if should_remove {
                self.left.pop();
                if remove_entry {
                    self.del_left.remove(&k);
                }
            }
        }
    }

    fn prune_right(&mut self) {
        loop {
            let Some(&Reverse(top)) = self.right.peek() else { break; };
            let k = Self::key(top.0);
            let mut should_remove = false;
            let mut remove_entry = false;

            if let Some(count) = self.del_right.get_mut(&k) {
                if *count > 0 {
                    *count -= 1;
                    should_remove = true;
                    if *count == 0 {
                        remove_entry = true;
                    }
                } else {
                    break;
                }
            } else {
                break;
            }

            if should_remove {
                self.right.pop();
                if remove_entry {
                    self.del_right.remove(&k);
                }
            }
        }
    }

    fn active_left_len(&self) -> usize {
        let pending: usize = self.del_left.values().sum();
        self.left.len().saturating_sub(pending)
    }

    fn active_right_len(&self) -> usize {
        let pending: usize = self.del_right.values().sum();
        self.right.len().saturating_sub(pending)
    }

    fn rebalance(&mut self) {
        let target_left = if self.active_count == 0 {
            0
        } else {
            ((self.active_count as f64) * self.phi).ceil() as usize
        };

        self.prune_left();
        self.prune_right();

        while self.active_left_len() > target_left {
            self.prune_left();
            if let Some(x) = self.left.pop() {
                self.right.push(Reverse(x));
            } else {
                break;
            }
        }

        while self.active_left_len() < target_left {
            self.prune_right();
            let Some(Reverse(x)) = self.right.pop() else { break; };
            self.left.push(x);
        }

        // Ensure heap invariant: max(left) <= min(right)
        self.prune_left();
        self.prune_right();

        if !self.left.is_empty() && !self.right.is_empty() {
            let left_max = *self.left.peek().unwrap();
            let right_min = self.right.peek().unwrap().0;

            if left_max > right_min {
                self.left.pop();
                self.right.pop();
                self.left.push(right_min);
                self.right.push(Reverse(left_max));
            }
        }
    }

    fn push(&mut self, value: f64) {
        // Add to time order queue (None for NaN, Some for valid values)
        let opt_value = if value.is_nan() { None } else { Some(value) };
        self.time_order.push_back(opt_value);

        // Only insert valid values into heaps
        if let Some(v) = opt_value {
            self.active_count += 1;

            let ordered = OrderedFloat(v);

            // Insert into appropriate heap
            self.prune_left();
            if self.left.is_empty() || v <= self.left.peek().unwrap().0 {
                self.left.push(ordered);
            } else {
                self.right.push(Reverse(ordered));
            }

            self.rebalance();
        }

        // Remove oldest if window is full
        if self.time_order.len() > self.window_size {
            let old_value = self.time_order.pop_front().unwrap();

            // Only process if it was a valid value
            if let Some(old_val) = old_value {
                self.active_count -= 1;

                let k = Self::key(old_val);

                // Determine which heap contains the old value
                self.prune_left();
                if !self.left.is_empty() && old_val <= self.left.peek().unwrap().0 {
                    *self.del_left.entry(k).or_insert(0) += 1;
                } else {
                    *self.del_right.entry(k).or_insert(0) += 1;
                }

                self.rebalance();
            }
        }
    }

    fn is_ready(&self) -> bool {
        // Ready once we have window_size updates (not just valid values)
        self.time_order.len() >= self.window_size && self.active_count > 0
    }

    /// Calculates quantile using R-7 method with interpolation.
    fn quantile_r7(&mut self) -> f64 {
        if self.active_count == 0 {
            return f64::NAN;
        }

        let n = self.active_count as f64;
        let h = (n - 1.0) * self.phi + 1.0;
        let k = h.floor();
        let g = h - k;

        self.prune_left();
        self.prune_right();

        // Handle edge cases
        if self.left.is_empty() {
            if self.right.is_empty() {
                return f64::NAN;
            }
            return self.right.peek().unwrap().0.0;
        }

        let q_low = self.left.peek().unwrap().0;

        if g == 0.0 || self.right.is_empty() {
            return q_low;
        }

        let q_high = self.right.peek().unwrap().0.0;
        (1.0 - g) * q_low + g * q_high
    }

    /// Resets internal state (clears heaps, deletion maps, and counters).
    fn reset(&mut self) {
        self.time_order.clear();
        self.left.clear();
        self.right.clear();
        self.del_left.clear();
        self.del_right.clear();
        self.active_count = 0;
    }
}
