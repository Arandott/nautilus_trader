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

//! Python bindings for FactorExpIndicator.

use pyo3::prelude::*;
use nautilus_model::{
    data::{Bar, QuoteTick, TradeTick},
    enums::PriceType,
};

use crate::{
    indicator::FactorExpIndicator,
    expression::{CompiledExpression, ExprNode, ExpressionError},
};

/// Python wrapper for FactorExpIndicator.
#[pyclass(name = "FactorExpIndicator", module = "nautilus_trader.core.nautilus_pyo3.indicators")]
pub struct PyFactorExpIndicator {
    inner: FactorExpIndicator,
    expression_str: String,
}

#[pymethods]
impl PyFactorExpIndicator {
    /// Creates a new FactorExpIndicator from an expression string.
    #[new]
    #[pyo3(signature = (expression, period=None, price_type=None))]
    fn py_new(expression: &str, period: Option<usize>, price_type: Option<PriceType>) -> PyResult<Self> {
        // For now, we'll create a simple expression parser
        // In a full implementation, this would use the Python parser and compile to Rust
        let compiled = parse_simple_expression(expression)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to parse expression: {}", e)
            ))?;
        
        // Auto-detect period if not provided
        let period = period.unwrap_or(compiled.metadata.max_window.max(1));
        let price_type = price_type.unwrap_or(PriceType::Last);
        
        Ok(Self {
            inner: FactorExpIndicator::new(compiled, period, price_type),
            expression_str: expression.to_string(),
        })
    }
    
    /// Returns the expression string.
    #[getter]
    fn expression(&self) -> &str {
        &self.expression_str
    }
    
    /// Returns the lookback period.
    #[getter]
    fn period(&self) -> usize {
        self.inner.period
    }
    
    /// Returns the current value.
    #[getter]
    fn value(&self) -> f64 {
        self.inner.value
    }
    
    /// Returns the count of updates.
    #[getter]
    fn count(&self) -> usize {
        self.inner.count
    }
    
    /// Returns whether the indicator is initialized.
    #[getter]
    fn initialized(&self) -> bool {
        self.inner.initialized
    }
    
    /// Handles a quote tick update.
    #[pyo3(name = "handle_quote_tick")]
    fn py_handle_quote_tick(&mut self, quote: &QuoteTick) {
        self.inner.handle_quote(quote);
    }
    
    /// Handles a trade tick update.
    #[pyo3(name = "handle_trade_tick")]
    fn py_handle_trade_tick(&mut self, trade: &TradeTick) {
        self.inner.handle_trade(trade);
    }
    
    /// Handles a bar update.
    #[pyo3(name = "handle_bar")]
    fn py_handle_bar(&mut self, bar: &Bar) {
        self.inner.handle_bar(bar);
    }
    
    /// Resets the indicator.
    #[pyo3(name = "reset")]
    fn py_reset(&mut self) {
        self.inner.reset();
    }
    
    fn __repr__(&self) -> String {
        format!("FactorExpIndicator('{}', period={})", self.expression_str, self.inner.period)
    }
}

/// Simple expression parser for testing.
/// In production, this would be replaced by the full Python parser.
fn parse_simple_expression(expression: &str) -> Result<CompiledExpression, ExpressionError> {
    // Handle simple feature references
    if expression.starts_with('$') {
        return Ok(CompiledExpression::new(ExprNode::Feature(expression.to_string())));
    }
    
    // Handle simple TS_Mean($close, N) pattern
    if expression.starts_with("TS_Mean(") && expression.ends_with(')') {
        let inner = &expression[8..expression.len()-1];
        let parts: Vec<&str> = inner.split(',').collect();
        
        if parts.len() == 2 {
            let feature = parts[0].trim();
            let window: f64 = parts[1].trim().parse()
                .map_err(|_| ExpressionError::ParseError("Invalid window size".to_string()))?;
            
            let mut params = std::collections::HashMap::new();
            params.insert("window".to_string(), window);
            
            return Ok(CompiledExpression::new(
                ExprNode::Operator {
                    name: "TS_Mean".to_string(),
                    args: vec![CompiledExpression::new(ExprNode::Feature(feature.to_string()))],
                    params,
                }
            ));
        }
    }
    
    // For other expressions, create a placeholder
    // In production, this would use the full Python parser
    Err(ExpressionError::ParseError(
        "Complex expression parsing not yet implemented in Rust. Use Python parser.".to_string()
    ))
}

/// Factory function to create and compile expressions from Python.
#[pyfunction]
#[pyo3(signature = (expression, metadata=None))]
pub fn compile_expression_from_python(
    expression: &str,
    metadata: Option<&pyo3::types::PyDict>,
) -> PyResult<String> {
    // This function would receive parsed expression data from Python
    // and compile it to a Rust representation
    // For now, it's a placeholder
    Ok(format!("Compiled: {}", expression))
}