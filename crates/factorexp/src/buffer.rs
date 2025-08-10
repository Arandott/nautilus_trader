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

//! High-performance rolling buffer implementation for streaming computations.

use arraydeque::{ArrayDeque, Wrapping};
use std::fmt::Display;

/// Maximum supported window size for operators
pub const MAX_WINDOW_SIZE: usize = 1_024;

/// A high-performance rolling buffer for streaming computations.
///
/// This buffer uses a fixed-size circular array for optimal cache performance
/// and minimal memory allocation.
#[derive(Debug, Clone)]
pub struct RollingBuffer {
    data: ArrayDeque<f64, MAX_WINDOW_SIZE, Wrapping>,
    window_size: usize,
    count: usize,
    sum: f64,
    sum_sq: f64,
}

impl RollingBuffer {
    /// Creates a new rolling buffer with the specified window size.
    ///
    /// # Panics
    ///
    /// Panics if `window_size` is 0 or exceeds `MAX_WINDOW_SIZE`.
    #[must_use]
    pub fn new(window_size: usize) -> Self {
        assert!(window_size > 0, "Window size must be positive");
        assert!(
            window_size <= MAX_WINDOW_SIZE,
            "Window size {} exceeds maximum {}",
            window_size,
            MAX_WINDOW_SIZE
        );

        Self {
            data: ArrayDeque::new(),
            window_size,
            count: 0,
            sum: 0.0,
            sum_sq: 0.0,
        }
    }

    /// Updates the buffer with a new value.
    ///
    /// Returns the value that was evicted from the buffer, if any.
    pub fn update(&mut self, value: f64) -> Option<f64> {
        let evicted = if self.is_full() {
            self.data.pop_front()
        } else {
            None
        };

        let _ = self.data.push_back(value);
        self.count += 1;

        // Update running statistics
        self.sum += value;
        self.sum_sq += value * value;

        if let Some(old_value) = evicted {
            self.sum -= old_value;
            self.sum_sq -= old_value * old_value;
        }

        evicted
    }

    /// Returns the current window as a Vec.
    /// Note: This allocates a new Vec to handle the circular buffer correctly.
    #[inline]
    #[must_use]
    pub fn window(&self) -> Vec<f64> {
        self.data.iter().copied().collect()
    }
    
    /// Returns the window as a pair of slices for advanced usage
    #[inline]
    #[must_use]
    pub fn window_slices(&self) -> (&[f64], &[f64]) {
        self.data.as_slices()
    }
    
    /// Alias for values() method for backward compatibility
    #[inline]
    #[must_use]
    pub fn as_slice(&self) -> Vec<f64> {
        self.values()
    }

    /// Returns all values in the buffer as a Vec
    #[inline]
    #[must_use]
    pub fn values(&self) -> Vec<f64> {
        self.data.iter().copied().collect()
    }

    /// Returns the window size.
    #[inline]
    #[must_use]
    pub const fn window_size(&self) -> usize {
        self.window_size
    }

    /// Returns the current size of the buffer.
    #[inline]
    #[must_use]
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// Returns true if the buffer is empty.
    #[inline]
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// Returns true if the buffer is full.
    #[inline]
    #[must_use]
    pub fn is_full(&self) -> bool {
        self.data.len() == self.window_size
    }

    /// Returns true if the buffer is ready for computation.
    #[inline]
    #[must_use]
    pub fn is_ready(&self) -> bool {
        self.is_full()
    }

    /// Returns the total count of values that have been added.
    #[inline]
    #[must_use]
    pub const fn count(&self) -> usize {
        self.count
    }

    /// Returns the current sum of values in the buffer.
    #[inline]
    #[must_use]
    pub const fn sum(&self) -> f64 {
        self.sum
    }

    /// Returns the current sum of squared values in the buffer.
    #[inline]
    #[must_use]
    pub const fn sum_sq(&self) -> f64 {
        self.sum_sq
    }

    /// Returns the mean of values in the buffer.
    #[inline]
    #[must_use]
    pub fn mean(&self) -> f64 {
        if self.is_empty() {
            0.0
        } else {
            self.sum / self.len() as f64
        }
    }

    /// Returns the variance of values in the buffer.
    #[inline]
    #[must_use]
    pub fn variance(&self, ddof: usize) -> f64 {
        let n = self.len();
        if n <= ddof {
            return 0.0;
        }

        let mean = self.mean();
        let var = (self.sum_sq / n as f64) - mean * mean;
        var * (n as f64 / (n - ddof) as f64)
    }

    /// Returns the standard deviation of values in the buffer.
    #[inline]
    #[must_use]
    pub fn std(&self, ddof: usize) -> f64 {
        self.variance(ddof).sqrt()
    }

    /// Returns the minimum value in the buffer.
    #[must_use]
    pub fn min(&self) -> Option<f64> {
        self.data.iter().copied().reduce(f64::min)
    }

    /// Returns the maximum value in the buffer.
    #[must_use]
    pub fn max(&self) -> Option<f64> {
        self.data.iter().copied().reduce(f64::max)
    }

    /// Returns the value at the given index.
    #[inline]
    #[must_use]
    pub fn get(&self, index: usize) -> Option<f64> {
        self.data.get(index).copied()
    }

    /// Returns the first (oldest) value in the buffer.
    #[inline]
    #[must_use]
    pub fn first(&self) -> Option<f64> {
        self.data.front().copied()
    }

    /// Returns the last (newest) value in the buffer.
    #[inline]
    #[must_use]
    pub fn last(&self) -> Option<f64> {
        self.data.back().copied()
    }

    /// Resets the buffer to empty state.
    pub fn reset(&mut self) {
        self.data.clear();
        self.count = 0;
        self.sum = 0.0;
        self.sum_sq = 0.0;
    }
    
    /// Alias for reset() method
    pub fn clear(&mut self) {
        self.reset();
    }
    
    /// Alias for update() method
    pub fn push(&mut self, value: f64) -> Option<f64> {
        self.update(value)
    }
}

impl Display for RollingBuffer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "RollingBuffer(window_size={}, len={}, count={})",
            self.window_size,
            self.len(),
            self.count
        )
    }
}

/// Statistics computed from a rolling buffer.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BufferStats {
    /// Number of values in the buffer
    pub count: usize,
    /// Mean of values
    pub mean: f64,
    /// Standard deviation
    pub std: f64,
    /// Minimum value
    pub min: f64,
    /// Maximum value
    pub max: f64,
}

impl BufferStats {
    /// Computes statistics from a rolling buffer.
    #[must_use]
    pub fn from_buffer(buffer: &RollingBuffer, ddof: usize) -> Self {
        Self {
            count: buffer.len(),
            mean: buffer.mean(),
            std: buffer.std(ddof),
            min: buffer.min().unwrap_or(0.0),
            max: buffer.max().unwrap_or(0.0),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rolling_buffer_basic() {
        let mut buffer = RollingBuffer::new(3);
        
        assert!(buffer.is_empty());
        assert!(!buffer.is_full());
        assert!(!buffer.is_ready());
        
        buffer.update(1.0);
        buffer.update(2.0);
        buffer.update(3.0);
        
        assert!(buffer.is_full());
        assert!(buffer.is_ready());
        assert_eq!(buffer.len(), 3);
        assert_eq!(buffer.sum(), 6.0);
        assert_eq!(buffer.mean(), 2.0);
    }

    #[test]
    fn test_rolling_buffer_eviction() {
        let mut buffer = RollingBuffer::new(2);
        
        buffer.update(1.0);
        buffer.update(2.0);
        let evicted = buffer.update(3.0);
        
        assert_eq!(evicted, Some(1.0));
        assert_eq!(buffer.sum(), 5.0);
        assert_eq!(buffer.mean(), 2.5);
    }

    #[test]
    fn test_buffer_stats() {
        let mut buffer = RollingBuffer::new(5);
        
        for i in 1..=5 {
            buffer.update(i as f64);
        }
        
        let stats = BufferStats::from_buffer(&buffer, 1);
        assert_eq!(stats.count, 5);
        assert_eq!(stats.mean, 3.0);
        assert!(stats.std > 1.58 && stats.std < 1.59);
        assert_eq!(stats.min, 1.0);
        assert_eq!(stats.max, 5.0);
    }
}