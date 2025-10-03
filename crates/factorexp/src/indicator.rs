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

#[cfg(feature = "extended_bar")]
use extended_bar_macros::{
    bool_get_by_name, price_get_by_name, quantity_get_by_name, u64_get_by_name,
};
#[cfg(feature = "extended_bar")]
use nautilus_model::data::extended_bar;
use nautilus_model::{
    data::{Bar, QuoteTick, TradeTick},
    enums::PriceType,
};
use std::collections::HashMap;

use crate::{buffer::RollingBuffer, engine::ComputationEngine, expression::CompiledExpression};

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
    /// Creates a new [`FactorExpIndicator`] instance using unified node architecture.
    pub fn new(expression: CompiledExpression, period: usize, price_type: PriceType) -> Self {
        // Initialize buffers for each feature
        let mut buffers = HashMap::new();
        for feature in &expression.metadata.features {
            buffers.insert(feature.clone(), RollingBuffer::new(period));
        }

        // Create engine and build expression tree for optimal performance
        let mut engine = ComputationEngine::new();
        if let Err(e) = engine.build_tree(&expression) {
            eprintln!(
                "Warning: Failed to build unified expression tree: {}. Falling back to compatibility mode.",
                e
            );
        }

        Self {
            expression,
            engine,
            buffers,
            period,
            price_type,
            value: f64::NAN,
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
            _ => HashMap::from([("price".to_string(), price.as_f64())]),
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
        #[allow(unused_mut)]
        let mut data = HashMap::from([
            ("open".to_string(), bar.open.as_f64()),
            ("high".to_string(), bar.high.as_f64()),
            ("low".to_string(), bar.low.as_f64()),
            ("close".to_string(), bar.close.as_f64()),
            ("volume".to_string(), bar.volume.as_f64()),
        ]);

        #[cfg(feature = "extended_bar")]
        insert_extended_fields(&mut data, bar);

        self.update_with_data(data);
    }

    /// Updates the indicator with new data using unified architecture.
    fn update_with_data(&mut self, data: HashMap<String, f64>) {
        // Update buffers with available features
        for (feature, value) in data {
            if let Some(buffer) = self.buffers.get_mut(&feature) {
                buffer.push(value);
            }
        }

        self.count += 1;

        // Try unified architecture first
        match self.engine.update_and_compute(&self.buffers) {
            Ok(Some(value)) => {
                // Valid value computed
                self.value = value;
                if !self.initialized {
                    self.initialized = true;
                }
            }
            Ok(None) => {
                // Not ready yet (warm-up period) - set to NaN
                if !self.initialized {
                    self.value = f64::NAN;
                }
                // Keep previous value if already initialized
            }
            Err(e) => {
                // Real error - log and keep previous value
                eprintln!("FactorExp computation error: {}", e);
            }
        }
    }

    /// Resets the indicator state.
    pub fn reset(&mut self) {
        self.value = f64::NAN;
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

#[cfg(feature = "extended_bar")]
fn insert_extended_fields(data: &mut HashMap<String, f64>, bar: &Bar) {
    use extended_bar::FieldType;

    for spec in extended_bar::field_specs() {
        let maybe_value = match spec.field_type {
            FieldType::Quantity => quantity_get_by_name!(bar, spec.ident)
                .map(|quantity: ::nautilus_model::types::Quantity| quantity.as_f64()),
            FieldType::Price => price_get_by_name!(bar, spec.ident)
                .map(|price: ::nautilus_model::types::Price| price.as_f64()),
            FieldType::U64 => u64_get_by_name!(bar, spec.ident).map(|value: u64| value as f64),
            FieldType::Bool => bool_get_by_name!(bar, spec.ident)
                .map(|value: bool| if value { 1.0 } else { 0.0 }),
        };

        if let Some(value) = maybe_value {
            data.insert(spec.ident.to_string(), value);
        }
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
    use nautilus_core::UnixNanos;
    use nautilus_model::{
        data::{BarSpecification, BarType},
        enums::{AggregationSource, BarAggregation, PriceType},
        identifiers::InstrumentId,
        types::{Price, Quantity},
    };

    #[cfg(feature = "extended_bar")]
    use super::insert_extended_fields;

    fn create_test_bar(close: f64) -> Bar {
        let instrument_id = InstrumentId::from("TEST/USDT.SIM");
        let bar_type = BarType::new(
            instrument_id,
            BarSpecification::new(1, BarAggregation::Minute, PriceType::Mid),
            AggregationSource::External,
        );

        nautilus_model::bar_new_with_defaults!(
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

    #[cfg(feature = "extended_bar")]
    fn create_extended_bar(close: f64, amt: f64) -> Bar {
        let mut bar = create_test_bar(close);
        // Preserve fractional values in the test helper by matching the precision
        // of the sample amount instead of forcing whole units.
        bar.amt = Quantity::new(amt, 1);
        bar
    }

    #[test]
    fn test_indicator_initialization() {
        let expr = CompiledExpression::new(ExprNode::Feature("$close".to_string()));

        let indicator = FactorExpIndicator::new(expr, 1, PriceType::Last);

        assert_eq!(indicator.period, 1);
        assert_eq!(indicator.count, 0);
        assert!(!indicator.initialized);
        assert!(indicator.value.is_nan());
    }

    #[test]
    fn test_indicator_bar_update() {
        let expr = CompiledExpression::new(ExprNode::Feature("$close".to_string()));

        let mut indicator = FactorExpIndicator::new(expr, 1, PriceType::Last);
        let bar = create_test_bar(100.0);

        indicator.handle_bar(&bar);

        assert_eq!(indicator.count, 1);
        assert!(indicator.initialized);
        assert_eq!(indicator.value, 100.0);
    }

    #[test]
    fn test_end_to_end_string_parsing_and_calculation() {
        // Test 1: Simple feature extraction
        let mut parser = crate::parser::Parser::new("$close");
        let parsed = parser.parse().expect("Failed to parse");
        let expr_node = crate::parser::convert_to_expr_node(parsed);
        let compiled = CompiledExpression::new(expr_node);

        let mut indicator = FactorExpIndicator::new(compiled, 1, PriceType::Last);
        indicator.handle_bar(&create_test_bar(100.0));
        assert_eq!(indicator.value, 100.0);

        // Test 2: Simple arithmetic
        let mut parser = crate::parser::Parser::new("$close + 10");
        let parsed = parser.parse().expect("Failed to parse");
        let expr_node = crate::parser::convert_to_expr_node(parsed);
        let compiled = CompiledExpression::new(expr_node);

        let mut indicator = FactorExpIndicator::new(compiled, 1, PriceType::Last);
        indicator.handle_bar(&create_test_bar(100.0));
        assert_eq!(indicator.value, 110.0);

        // Test 3: Rolling mean (requires multiple bars)
        let mut parser = crate::parser::Parser::new("TS_Mean($close, 3)");
        let parsed = parser.parse().expect("Failed to parse");
        let expr_node = crate::parser::convert_to_expr_node(parsed);
        let compiled = CompiledExpression::new(expr_node);

        let mut indicator = FactorExpIndicator::new(compiled, 3, PriceType::Last);
        indicator.handle_bar(&create_test_bar(100.0));
        indicator.handle_bar(&create_test_bar(110.0));
        indicator.handle_bar(&create_test_bar(120.0));
        assert_eq!(indicator.value, 110.0); // Mean of [100, 110, 120]

        // Test 4: Complex expression
        let mut parser = crate::parser::Parser::new("($close - $open) / 2");
        let parsed = parser.parse().expect("Failed to parse");
        let expr_node = crate::parser::convert_to_expr_node(parsed);
        let compiled = CompiledExpression::new(expr_node);

        let mut indicator = FactorExpIndicator::new(compiled, 1, PriceType::Last);
        indicator.handle_bar(&create_test_bar(100.0)); // open=99, close=100
        assert_eq!(indicator.value, 0.5); // (100 - 99) / 2
    }

    #[cfg(feature = "extended_bar")]
    #[test]
    fn test_insert_extended_fields_includes_quantity() {
        let bar = create_extended_bar(100.0, 250.5);
        let mut data = std::collections::HashMap::new();

        insert_extended_fields(&mut data, &bar);

        // prirnt out the bar'amt field value for debugging
        println!("bar.amt: {:?}", bar.amt);

        assert_eq!(data.get("amt"), Some(&250.5));
    }

    #[cfg(feature = "extended_bar")]
    #[test]
    fn test_indicator_reads_extended_quantity_feature() {
        let expr = CompiledExpression::new(ExprNode::Feature("$amt".to_string()));
        let mut indicator = FactorExpIndicator::new(expr, 1, PriceType::Last);
        let bar = create_extended_bar(100.0, 512.0);

        indicator.handle_bar(&bar);

        assert_eq!(indicator.count, 1);
        assert!(indicator.initialized);
        assert_eq!(indicator.value, 512.0);
    }
}
