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
    pub fn update_internal(&mut self, value: f64) {
        self.base.buffer_mut().update(value);
        
        if self.base.buffer().is_ready() {
            let window = self.base.buffer().window();
            let mean = self.base.buffer().mean();
            
            let mut sum_abs_dev = 0.0;
            for &val in window {
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
    pub fn update_internal(&mut self, value: f64) {
        self.base.buffer_mut().update(value);
        
        if self.base.buffer().is_ready() {
            let product = self.base.buffer().window().iter().product();
            self.base.set_value(product);
        }
    }
}

/// Rolling percentage change operator.
#[derive(Debug)]
pub struct PctChange {
    base: BaseOperator,
}

impl PctChange {
    /// Creates a new percentage change operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        Self {
            base: BaseOperator::new("TS_PctChg", window_size),
        }
    }
}

impl_rolling_operator_common!(PctChange);

impl PctChange {
    pub fn update_internal(&mut self, value: f64) {
        self.base.buffer_mut().update(value);
        
        if self.base.buffer().len() >= 2 {
            if let (Some(first), Some(last)) = (
                self.base.buffer().first(),
                self.base.buffer().last(),
            ) {
                let pct_change = if first.abs() < f64::EPSILON {
                    if last.abs() < f64::EPSILON {
                        0.0
                    } else if last > 0.0 {
                        1.0
                    } else {
                        -1.0
                    }
                } else {
                    (last - first) / first.abs()
                };
                
                self.base.set_value(pct_change);
            }
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

    #[test]
    fn test_pct_change_operator() {
        let mut pct = PctChange::new(5);
        
        pct.update(100.0);
        pct.update(110.0);
        
        // (110 - 100) / 100 = 0.1
        assert!((pct.value() - 0.1).abs() < 1e-10);
        
        pct.update(120.0);
        pct.update(130.0);
        pct.update(150.0);
        
        // (150 - 100) / 100 = 0.5
        assert!((pct.value() - 0.5).abs() < 1e-10);
    }
}