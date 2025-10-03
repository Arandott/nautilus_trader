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

//! Advanced statistical operators (skewness, kurtosis, MAD, etc.).

use crate::{
    impl_rolling_operator_common,
    operators::{BaseOperator, RollingOperator},
};

/// Rolling skewness operator.
#[derive(Debug)]
pub struct Skew {
    base: BaseOperator,
}

impl Skew {
    /// Creates a new rolling skewness operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Skew", window_size),
        }
    }
}

impl_rolling_operator_common!(Skew);

impl Skew {
    /// Updates the operator with a new value and recalculates the skewness.
    pub fn update_internal(&mut self, value: f64) {
        self.base.buffer_mut().update(value);

        if self.base.buffer().len() >= 3 {
            let window = self.base.buffer().window();
            let n = window.len() as f64;
            let mean = self.base.buffer().mean();
            let std = self.base.buffer().std(0);

            if std > 0.0 {
                let mut sum_cubed = 0.0;
                for &val in &window {
                    let diff = val - mean;
                    sum_cubed += diff * diff * diff;
                }

                let skewness = (sum_cubed / n) / (std * std * std);
                self.base.set_value(skewness);
            } else {
                self.base.set_value(0.0);
            }
        }
    }
}

/// Rolling kurtosis operator.
#[derive(Debug)]
pub struct Kurtosis {
    base: BaseOperator,
}

impl Kurtosis {
    /// Creates a new rolling kurtosis operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Kurt", window_size),
        }
    }
}

impl_rolling_operator_common!(Kurtosis);

impl Kurtosis {
    /// Updates the operator with a new value and recalculates the kurtosis.
    pub fn update_internal(&mut self, value: f64) {
        self.base.buffer_mut().update(value);

        if self.base.buffer().len() >= 4 {
            let window = self.base.buffer().window();
            let n = window.len() as f64;
            let mean = self.base.buffer().mean();
            let std = self.base.buffer().std(0);

            if std > 0.0 {
                let mut sum_fourth = 0.0;
                for &val in &window {
                    let diff = val - mean;
                    sum_fourth += diff * diff * diff * diff;
                }

                let kurtosis = (sum_fourth / n) / (std * std * std * std) - 3.0;
                self.base.set_value(kurtosis);
            } else {
                self.base.set_value(0.0);
            }
        }
    }
}

/// Mean Absolute Deviation operator.
#[derive(Debug)]
pub struct Mad {
    base: BaseOperator,
}

impl Mad {
    /// Creates a new MAD operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_Mad", window_size),
        }
    }
}

impl_rolling_operator_common!(Mad);

impl Mad {
    /// Updates the operator with a new value and recalculates the mean absolute deviation.
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
            let window = self.base.buffer().window();
            let mean = self.base.buffer().mean();

            let mut sum_abs_dev = 0.0;
            for val in &window {
                sum_abs_dev += (val - mean).abs();
            }

            let mad = sum_abs_dev / window.len() as f64;
            self.base.set_value(mad);
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
    /// Updates the operator with a new value and recalculates the product.
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
            let product = self.base.buffer().window().iter().product();
            self.base.set_value(product);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mad_operator() {
        let mut mad = Mad::new(5);

        // Data: [1, 2, 3, 4, 5]
        // Mean: 3
        // MAD: (|1-3| + |2-3| + |3-3| + |4-3| + |5-3|) / 5 = 6/5 = 1.2
        for i in 1..=5 {
            mad.update(i as f64);
        }

        assert!(mad.is_ready());
        assert!((mad.value() - 1.2).abs() < 1e-10);
    }

    #[test]
    fn test_product_operator() {
        let mut prod = Product::new(3);

        prod.update(2.0);
        prod.update(3.0);
        prod.update(4.0);

        assert!(prod.is_ready());
        assert_eq!(prod.value(), 24.0); // 2 * 3 * 4

        prod.update(5.0);
        assert_eq!(prod.value(), 60.0); // 3 * 4 * 5
    }
}
