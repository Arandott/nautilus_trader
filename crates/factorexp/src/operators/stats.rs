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
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Skewness requires at least 3 valid values
        let valid_len = self.base.buffer().valid_len();
        if valid_len < 3 {
            // Not enough valid values: reuse last valid skewness
            self.base.set_stale_value();
            return;
        }

        // Use NaN-aware mean and std from buffer
        let mean = self.base.buffer().mean();
        let std = self.base.buffer().std(0);

        // Check for zero variance case
        if std.is_nan() || std <= 0.0 {
            // Zero variance: reuse last valid skewness
            self.base.set_stale_value();
            return;
        }

        // Compute skewness using only valid values
        let mut sum_cubed = 0.0;
        for val in self.base.buffer().iter_valid() {
            let diff = val - mean;
            sum_cubed += diff * diff * diff;
        }

        let n = valid_len as f64;
        let skewness = (sum_cubed / n) / (std * std * std);
        self.base.set_value(skewness);
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
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Kurtosis requires at least 4 valid values
        let valid_len = self.base.buffer().valid_len();
        if valid_len < 4 {
            // Not enough valid values: reuse last valid kurtosis
            self.base.set_stale_value();
            return;
        }

        // Use NaN-aware mean and std from buffer
        let mean = self.base.buffer().mean();
        let std = self.base.buffer().std(0);

        // Check for zero variance case
        if std.is_nan() || std <= 0.0 {
            // Zero variance: reuse last valid kurtosis
            self.base.set_stale_value();
            return;
        }

        // Compute kurtosis using only valid values
        let mut sum_fourth = 0.0;
        for val in self.base.buffer().iter_valid() {
            let diff = val - mean;
            sum_fourth += diff * diff * diff * diff;
        }

        let n = valid_len as f64;
        // Excess kurtosis (subtract 3 for normal distribution baseline)
        let kurtosis = (sum_fourth / n) / (std * std * std * std) - 3.0;
        self.base.set_value(kurtosis);
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
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid MAD
            self.base.set_stale_value();
            return;
        }

        // Compute MAD from valid values only
        let valid_values = self.base.buffer().values_valid();
        let mean = self.base.buffer().mean();

        let mut sum_abs_dev = 0.0;
        for val in &valid_values {
            sum_abs_dev += (val - mean).abs();
        }

        let mad = sum_abs_dev / valid_values.len() as f64;
        self.base.set_value(mad);
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
        // Always advance the window, even for NaN
        let _ = self.base.buffer_mut().update(value);

        // Check if we have any valid values in the current window
        if self.base.buffer().valid_len() == 0 {
            // No valid values: reuse last valid product
            self.base.set_stale_value();
            return;
        }

        // Compute product from valid values (filter NaN)
        let product = self.base.buffer().iter_valid().product();
        self.base.set_value(product);
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

    #[test]
    fn test_skew_nan_handling() {
        let mut skew = Skew::new(5);

        // Test with mixed valid and NaN values
        skew.update(1.0);
        skew.update(f64::NAN); // NaN should be filtered
        skew.update(2.0);
        skew.update(3.0);
        skew.update(4.0);

        // Should compute skewness using only valid values [1, 2, 3, 4]
        assert!(skew.is_ready());
        let skew_value = skew.value();
        assert!(skew_value.is_finite(), "Skewness should be finite with valid values");

        // Test insufficient valid values (< 3)
        let mut skew2 = Skew::new(5);
        skew2.update(1.0);
        skew2.update(f64::NAN);
        skew2.update(f64::NAN);
        skew2.update(2.0);
        skew2.update(f64::NAN);

        // Only 2 valid values, should reuse stale value (NaN since never set)
        assert!(skew2.is_ready());
        assert!(skew2.value().is_nan(), "Should return NaN with insufficient valid values");
    }

    #[test]
    fn test_skew_zero_variance() {
        let mut skew = Skew::new(5);

        // All same values = zero variance
        for _ in 0..5 {
            skew.update(10.0);
        }

        assert!(skew.is_ready());
        // Zero variance case should reuse stale value (NaN since never set)
        assert!(skew.value().is_nan(), "Should return NaN for zero variance");
    }

    #[test]
    fn test_kurtosis_nan_handling() {
        let mut kurt = Kurtosis::new(6);

        // Test with mixed valid and NaN values
        kurt.update(1.0);
        kurt.update(f64::NAN); // NaN should be filtered
        kurt.update(2.0);
        kurt.update(3.0);
        kurt.update(4.0);
        kurt.update(5.0);

        // Should compute kurtosis using only valid values [1, 2, 3, 4, 5]
        assert!(kurt.is_ready());
        let kurt_value = kurt.value();
        assert!(
            kurt_value.is_finite(),
            "Kurtosis should be finite with valid values"
        );

        // Test insufficient valid values (< 4)
        let mut kurt2 = Kurtosis::new(6);
        kurt2.update(1.0);
        kurt2.update(f64::NAN);
        kurt2.update(2.0);
        kurt2.update(f64::NAN);
        kurt2.update(3.0);
        kurt2.update(f64::NAN);

        // Only 3 valid values, should reuse stale value (NaN since never set)
        assert!(kurt2.is_ready());
        assert!(
            kurt2.value().is_nan(),
            "Should return NaN with insufficient valid values"
        );
    }

    #[test]
    fn test_kurtosis_zero_variance() {
        let mut kurt = Kurtosis::new(6);

        // All same values = zero variance
        for _ in 0..6 {
            kurt.update(10.0);
        }

        assert!(kurt.is_ready());
        // Zero variance case should reuse stale value (NaN since never set)
        assert!(kurt.value().is_nan(), "Should return NaN for zero variance");
    }
}
