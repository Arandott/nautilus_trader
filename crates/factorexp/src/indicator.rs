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

//! FactorExp indicator implementation.

use std::collections::HashMap;
use nautilus_model::{
    data::{Bar, QuoteTick, TradeTick},
    enums::PriceType,
};

use crate::{
    buffer::RollingBuffer,
    expression::CompiledExpression,
    engine::ComputationEngine,
};

/// A high-performance indicator that evaluates FactorExp expressions.
#[derive(Debug)]
pub struct FactorExpIndicator {
    /// The compiled expression to evaluate.
    expression: CompiledExpression,
    /// The computation engine.
    engine: ComputationEngine,
    /// Buffers for each feature.
    buffers: HashMap<String, RollingBuffer>,
    /// The lookback period.
    pub period: usize,
    /// The price type for quote ticks.
    pub price_type: PriceType,
    /// The current indicator value.
    pub value: f64,
    /// The count of updates.
    pub count: usize,
    /// Whether the indicator is initialized.
    pub initialized: bool,
}

impl FactorExpIndicator {
    /// Creates a new [`FactorExpIndicator`] instance.
    pub fn new(expression: CompiledExpression, period: usize, price_type: PriceType) -> Self {
        // Initialize buffers for each feature
        let mut buffers = HashMap::new();
        for feature in &expression.metadata.features {
            buffers.insert(feature.clone(), RollingBuffer::new(period));
        }
        
        Self {
            expression,
            engine: ComputationEngine::new(),
            buffers,
            period,
            price_type,
            value: 0.0,
            count: 0,
            initialized: false,
        }
    }
    
    /// Handles a quote tick update.
    pub fn handle_quote(&mut self, quote: &QuoteTick) {
        let price = quote.extract_price(self.price_type);
        
        // Create data map based on price type
        let data = match self.price_type {
            PriceType::Bid => HashMap::from([
                ("bid".to_string(), quote.bid_price.as_f64()),
                ("price".to_string(), price.as_f64()),
            ]),
            PriceType::Ask => HashMap::from([
                ("ask".to_string(), quote.ask_price.as_f64()),
                ("price".to_string(), price.as_f64()),
            ]),
            PriceType::Mid => HashMap::from([
                ("mid".to_string(), price.as_f64()),
                ("price".to_string(), price.as_f64()),
            ]),
            _ => HashMap::from([
                ("price".to_string(), price.as_f64()),
            ]),
        };
        
        self.update_with_data(data);
    }
    
    /// Handles a trade tick update.
    pub fn handle_trade(&mut self, trade: &TradeTick) {
        let data = HashMap::from([
            ("price".to_string(), trade.price.as_f64()),
            ("size".to_string(), trade.size.as_f64()),
        ]);
        
        self.update_with_data(data);
    }
    
    /// Handles a bar update.
    pub fn handle_bar(&mut self, bar: &Bar) {
        let data = HashMap::from([
            ("open".to_string(), bar.open.as_f64()),
            ("high".to_string(), bar.high.as_f64()),
            ("low".to_string(), bar.low.as_f64()),
            ("close".to_string(), bar.close.as_f64()),
            ("volume".to_string(), bar.volume.as_f64()),
        ]);
        
        self.update_with_data(data);
    }
    
    /// Updates the indicator with new data.
    fn update_with_data(&mut self, data: HashMap<String, f64>) {
        // Update buffers with available features
        for (feature, value) in data {
            if let Some(buffer) = self.buffers.get_mut(&feature) {
                buffer.push(value);
            }
        }
        
        self.count += 1;
        
        // Compute if we have enough data
        if self.count >= self.period {
            match self.engine.compute(&self.expression, &self.buffers) {
                Ok(value) => {
                    self.value = value;
                    if !self.initialized {
                        self.initialized = true;
                    }
                }
                Err(e) => {
                    // Log error but keep previous value
                    eprintln!("FactorExp computation error: {}", e);
                }
            }
        }
    }
    
    /// Resets the indicator state.
    pub fn reset(&mut self) {
        self.value = 0.0;
        self.count = 0;
        self.initialized = false;
        
        // Clear all buffers
        for buffer in self.buffers.values_mut() {
            buffer.clear();
        }
        
        // Reset engine
        self.engine.reset();
    }
}

/// Trait for factor-based indicators.
pub trait FactorIndicator {
    /// Handles a quote tick.
    fn handle_quote(&mut self, quote: &QuoteTick);
    
    /// Handles a trade tick.
    fn handle_trade(&mut self, trade: &TradeTick);
    
    /// Handles a bar.
    fn handle_bar(&mut self, bar: &Bar);
    
    /// Returns the current value.
    fn value(&self) -> f64;
    
    /// Returns whether the indicator is initialized.
    fn is_initialized(&self) -> bool;
    
    /// Resets the indicator.
    fn reset(&mut self);
}

impl FactorIndicator for FactorExpIndicator {
    fn handle_quote(&mut self, quote: &QuoteTick) {
        self.handle_quote(quote);
    }
    
    fn handle_trade(&mut self, trade: &TradeTick) {
        self.handle_trade(trade);
    }
    
    fn handle_bar(&mut self, bar: &Bar) {
        self.handle_bar(bar);
    }
    
    fn value(&self) -> f64 {
        self.value
    }
    
    fn is_initialized(&self) -> bool {
        self.initialized
    }
    
    fn reset(&mut self) {
        self.reset();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expression::{CompiledExpression, ExprNode};
    use nautilus_model::{
        types::{Price, Quantity},
        identifiers::{InstrumentId, BarType},
        data::{BarSpecification},
        enums::{BarAggregation, AggregationSource},
    };
    use nautilus_core::nanos::UnixNanos;
    
    fn create_test_bar(close: f64) -> Bar {
        let instrument_id = InstrumentId::from("TEST/USDT.SIM");
        let bar_type = BarType::new(
            instrument_id,
            BarSpecification::new(1, BarAggregation::Minute, PriceType::Mid),
            AggregationSource::External,
        );
        
        Bar::new(
            bar_type,
            Price::new(close - 1.0, 2),
            Price::new(close + 1.0, 2),
            Price::new(close - 2.0, 2),
            Price::new(close, 2),
            Quantity::new(1000.0, 0),
            UnixNanos::from(0),
            UnixNanos::from(0),
        )
    }
    
    #[test]
    fn test_indicator_initialization() {
        let expr = CompiledExpression::new(
            ExprNode::Feature("$close".to_string())
        );
        
        let indicator = FactorExpIndicator::new(expr, 1, PriceType::Last);
        
        assert_eq!(indicator.period, 1);
        assert_eq!(indicator.count, 0);
        assert!(!indicator.initialized);
        assert_eq!(indicator.value, 0.0);
    }
    
    #[test]
    fn test_indicator_bar_update() {
        let expr = CompiledExpression::new(
            ExprNode::Feature("$close".to_string())
        );
        
        let mut indicator = FactorExpIndicator::new(expr, 1, PriceType::Last);
        let bar = create_test_bar(100.0);
        
        indicator.handle_bar(&bar);
        
        assert_eq!(indicator.count, 1);
        assert!(indicator.initialized);
        assert_eq!(indicator.value, 100.0);
    }
}