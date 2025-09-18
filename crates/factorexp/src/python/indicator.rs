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
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

// Import from nautilus_model with python feature
use nautilus_model::{
    data::{Bar, QuoteTick, TradeTick},
    enums::PriceType,
};

use crate::{
    indicator::FactorExpIndicator,
    expression::{CompiledExpression, ExprNode, ExpressionError},
};

/// Python wrapper for FactorExpIndicator.
#[pyclass(name = "FactorExpIndicator", module = "nautilus_trader.core.nautilus_pyo3.factorexp")]
pub struct PyFactorExpIndicator {
    inner: FactorExpIndicator,
    expression_str: String,
}

#[pymethods]
impl PyFactorExpIndicator {
    /// Creates a new FactorExpIndicator from an expression string or compiled AST.
    #[new]
    #[pyo3(signature = (expression, period=None, price_type=None))]
    fn py_new(
        py: Python,
        expression: &str,
        period: Option<usize>,
        price_type: Option<&str>,
    ) -> PyResult<Self> {
        // Parse expression directly in Rust using the full parser
        let mut parser = crate::parser::Parser::new(expression);
        let parsed_expr = parser.parse()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to parse expression: {}", e)
            ))?;

        // Convert from parser's Expr to expression's ExprNode
        let expr_node = crate::parser::convert_to_expr_node(parsed_expr);
        let compiled = CompiledExpression::new(expr_node);
        
        // Auto-detect period if not provided
        let period = period.unwrap_or(compiled.metadata.max_window.max(1));
        
        // Parse price_type string to PriceType enum
        let price_type = if let Some(price_type_str) = price_type {
            parse_price_type(price_type_str)?
        } else {
            PriceType::Last
        };
        
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


/// Parse a string to PriceType enum.
fn parse_price_type(price_type_str: &str) -> PyResult<PriceType> {
    match price_type_str {
        "BID" => Ok(PriceType::Bid),
        "ASK" => Ok(PriceType::Ask),
        "MID" => Ok(PriceType::Mid),
        "LAST" => Ok(PriceType::Last),
        "MARK" => Ok(PriceType::Mark),
        _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Invalid PriceType string: '{}'. Valid values are: BID, ASK, MID, LAST, MARK", price_type_str)
        ))
    }
}