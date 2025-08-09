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

//! Moving average operators (EMA, WMA, etc.).

use crate::operators::RollingOperator;

/// Exponential Moving Average operator.
#[derive(Debug)]
pub struct Ema {
    name: String,
    window_size: usize,
    alpha: f64,
    value: f64,
    count: usize,
    initialized: bool,
}

impl Ema {
    /// Creates a new EMA operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        let alpha = 2.0 / (window_size as f64 + 1.0);
        
        Self {
            name: "TS_EMA".to_string(),
            window_size,
            alpha,
            value: 0.0,
            count: 0,
            initialized: false,
        }
    }
}

impl RollingOperator for Ema {
    fn name(&self) -> &str {
        &self.name
    }

    fn window_size(&self) -> usize {
        self.window_size
    }

    fn is_ready(&self) -> bool {
        self.initialized
    }

    fn value(&self) -> f64 {
        self.value
    }

    fn count(&self) -> usize {
        self.count
    }

    fn update(&mut self, value: f64) {
        self.count += 1;
        
        if !self.initialized {
            self.value = value;
            self.initialized = true;
        } else {
            self.value = self.alpha * value + (1.0 - self.alpha) * self.value;
        }
    }

    fn reset(&mut self) {
        self.value = 0.0;
        self.count = 0;
        self.initialized = false;
    }
}

/// Weighted Moving Average operator.
#[derive(Debug)]
pub struct Wma {
    name: String,
    window_size: usize,
    buffer: Vec<f64>,
    weights: Vec<f64>,
    weight_sum: f64,
    value: f64,
    count: usize,
}

impl Wma {
    /// Creates a new WMA operator.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        // Create linear weights: [1, 2, 3, ..., n]
        let weights: Vec<f64> = (1..=window_size).map(|i| i as f64).collect();
        let weight_sum: f64 = weights.iter().sum();
        
        Self {
            name: "TS_WMA".to_string(),
            window_size,
            buffer: Vec::with_capacity(window_size),
            weights,
            weight_sum,
            value: 0.0,
            count: 0,
        }
    }
}

impl RollingOperator for Wma {
    fn name(&self) -> &str {
        &self.name
    }

    fn window_size(&self) -> usize {
        self.window_size
    }

    fn is_ready(&self) -> bool {
        self.buffer.len() == self.window_size
    }

    fn value(&self) -> f64 {
        self.value
    }

    fn count(&self) -> usize {
        self.count
    }

    fn update(&mut self, value: f64) {
        self.count += 1;
        
        if self.buffer.len() == self.window_size {
            self.buffer.remove(0);
        }
        self.buffer.push(value);
        
        if self.buffer.len() == self.window_size {
            // Compute weighted average
            let mut sum = 0.0;
            for (i, &val) in self.buffer.iter().enumerate() {
                sum += val * self.weights[i];
            }
            self.value = sum / self.weight_sum;
        }
    }

    fn reset(&mut self) {
        self.buffer.clear();
        self.value = 0.0;
        self.count = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ema_operator() {
        let mut ema = Ema::new(5);
        
        assert!(!ema.is_ready());
        
        // First value initializes EMA
        ema.update(10.0);
        assert!(ema.is_ready());
        assert_eq!(ema.value(), 10.0);
        
        // Subsequent values update using alpha
        ema.update(20.0);
        let expected = 10.0 * (2.0/3.0) + 20.0 * (1.0/3.0);
        assert!((ema.value() - expected).abs() < 1e-10);
    }

    #[test]
    fn test_wma_operator() {
        let mut wma = Wma::new(3);
        
        assert!(!wma.is_ready());
        
        wma.update(1.0);
        wma.update(2.0);
        wma.update(3.0);
        
        assert!(wma.is_ready());
        // WMA = (1*1 + 2*2 + 3*3) / (1+2+3) = 14/6 = 2.333...
        assert!((wma.value() - 2.333333).abs() < 1e-5);
        
        wma.update(4.0);
        // WMA = (2*1 + 3*2 + 4*3) / 6 = 20/6 = 3.333...
        assert!((wma.value() - 3.333333).abs() < 1e-5);
    }
}