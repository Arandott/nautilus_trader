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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            // Keep current value (either NaN if not ready, or last valid value)
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            self.base.set_value(self.base.buffer().mean());
        }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            self.base.set_value(self.base.buffer().sum());
        }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            self.base.set_value(self.base.buffer().std(self.ddof));
        }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            self.base.set_value(self.base.buffer().variance(self.ddof));
        }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            if let Some(min) = self.base.buffer().min() {
                self.base.set_value(min);
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            if let Some(max) = self.base.buffer().max() {
                self.base.set_value(max);
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            let mut sorted: Vec<f64> = self.base.buffer().window();
            sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mid = sorted.len() / 2;
            
            let median = if sorted.len() % 2 == 0 {
                (sorted[mid - 1] + sorted[mid]) / 2.0
            } else {
                sorted[mid]
            };
            
            self.base.set_value(median);
        }
    }
}

/// Rolling delta (difference) operator.
#[derive(Debug)]
pub struct Delta {
    base: BaseOperator,
}

impl Delta {
    /// Creates a new rolling delta operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Delta", window_size),
        }
    }
}

impl_rolling_operator_common!(Delta);

impl Delta {
    /// Updates the operator with a new value and calculates the delta (difference).
    pub fn update_internal(&mut self, value: f64) {
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples (at least 2)
        if self.base.valid_count() >= 2 {
            let len = self.base.buffer().len();
            if len >= 2 {
                if let (Some(previous), Some(current)) = (
                    self.base.buffer().get(len - 2),
                    self.base.buffer().get(len - 1),
                ) {
                    self.base.set_value(current - previous);
                }
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() > self.period {
            // Get value from N periods ago (counting from current position)
            // For period=1: current is at len-1, 1 period ago is at len-1-1 = len-2
            let len = self.base.buffer().len();
            if len > self.period {
                let ref_index = len - 1 - self.period;
                if let Some(ref_value) = self.base.buffer().get(ref_index) {
                    self.base.set_value(ref_value);
                }
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            let values = self.base.buffer().window();
            let current_value = values[values.len() - 1]; // Use latest value in buffer
            
            // Count how many values are less than current value
            let smaller_count = values.iter()
                .filter(|&&x| x < current_value)
                .count() as f64;
            
            // Normalize rank to [0, 1] range
            // 0 = smallest value, 1 = largest value
            let rank = if values.len() <= 1 {
                0.0
            } else {
                smaller_count / (values.len() - 1) as f64
            };
            
            self.base.set_value(rank);
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            let values = self.base.buffer().window();
            
            if let Some((argmax_idx, _)) = values.iter()
                .enumerate()
                .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap()) {
                self.base.set_value(argmax_idx as f64);
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            let values = self.base.buffer().window();
            
            if let Some((argmin_idx, _)) = values.iter()
                .enumerate()
                .min_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap()) {
                self.base.set_value(argmin_idx as f64);
            }
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
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Valid value: push to buffer and increment valid count
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            let product = self.base.buffer()
                .window()
                .iter()
                .fold(1.0, |acc, &x| acc * x);
            self.base.set_value(product);
        }
    }
}

/// Rolling ZScore operator (standardization).
/// Computes (value - mean) / std over a rolling window.
#[derive(Debug)]
pub struct ZScore {
    base: BaseOperator,
    sum: f64,
    sum_sq: f64,
    ddof: usize,
}

impl ZScore {
    /// Creates a new rolling ZScore operator.
    #[must_use]
    pub fn new(window_size: usize, ddof: usize) -> Self {
        Self {
            base: BaseOperator::new("ZScore", window_size),
            sum: 0.0,
            sum_sq: 0.0,
            ddof,
        }
    }
}

impl_rolling_operator_common!(ZScore);

impl ZScore {
    /// Updates the operator with a new value and calculates ZScore.
    pub fn update_internal(&mut self, value: f64) {
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Check if buffer is full and we need to subtract old value
        if self.base.buffer().is_full() {
            if let Some(old_value) = self.base.buffer().get(0) {
                self.sum -= old_value;
                self.sum_sq -= old_value * old_value;
            }
        }
        
        // Add new value to buffer and running sums
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        self.sum += value;
        self.sum_sq += value * value;
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            // Use the actual buffer count, not valid_count for window calculations
            let n = self.base.buffer().count().min(self.base.buffer().window_size()) as f64;
            let mean = self.sum / n;
            
            // Calculate standard deviation with safety checks
            let denom = n - self.ddof as f64;
            if denom <= 0.0 {
                // Not enough degrees of freedom for std calculation
                self.base.set_value(f64::NAN);
                return;
            }
            
            let variance = (self.sum_sq - self.sum * self.sum / n) / denom;
            
            if variance > 0.0 {
                let std = variance.sqrt();
                // ZScore = (current_value - mean) / std
                let zscore = (value - mean) / std;
                self.base.set_value(zscore);
            } else {
                // No variation or negative variance (numerical error), zscore is undefined
                self.base.set_value(f64::NAN);
            }
        }
    }
}

/// Rolling Demean operator.
/// Computes value - rolling_mean over a window.
#[derive(Debug)]
pub struct Demean {
    base: BaseOperator,
    sum: f64,
}

impl Demean {
    /// Creates a new rolling Demean operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("Demean", window_size),
            sum: 0.0,
        }
    }
}

impl_rolling_operator_common!(Demean);

impl Demean {
    /// Updates the operator with a new value and calculates demeaned value.
    pub fn update_internal(&mut self, value: f64) {
        // Handle NaN input: don't push to buffer, return last valid value
        if value.is_nan() {
            return;
        }
        
        // Check if buffer is full and we need to subtract old value
        if self.base.buffer().is_full() {
            if let Some(old_value) = self.base.buffer().get(0) {
                self.sum -= old_value;
            }
        }
        
        // Add new value to buffer and running sum
        self.base.buffer_mut().update(value);
        self.base.increment_valid_count();
        self.sum += value;
        
        // Only compute if we have enough valid samples
        if self.base.valid_count() >= self.base.buffer().window_size() {
            // Use the actual buffer count, not valid_count for window mean
            let n = self.base.buffer().count().min(self.base.buffer().window_size()) as f64;
            let mean = self.sum / n;
            // Demeaned value = current_value - mean
            let demeaned = value - mean;
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
}