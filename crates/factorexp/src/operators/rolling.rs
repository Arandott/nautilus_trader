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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().is_ready() {
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
        self.base.buffer_mut().update(value);
        if self.base.buffer().len() >= 2 {
            if let (Some(first), Some(last)) = (
                self.base.buffer().first(),
                self.base.buffer().last(),
            ) {
                self.base.set_value(last - first);
            }
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
        assert_eq!(op.value(), 0.0);
        
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
}