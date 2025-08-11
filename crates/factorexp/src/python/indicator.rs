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
    #[pyo3(signature = (expression, period=None, price_type=None, compiled_ast=None))]
    fn py_new(
        py: Python,
        expression: &str,
        period: Option<usize>,
        price_type: Option<PriceType>,
        compiled_ast: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        // If compiled AST is provided, use it; otherwise try simple parsing
        let compiled = if let Some(ast_dict) = compiled_ast {
            // Convert the Python AST dictionary to Rust CompiledExpression
            let node = dict_to_expr_node(py, ast_dict)?;
            CompiledExpression::new(node)
        } else {
            // Fallback to simple parsing for basic expressions
            parse_simple_expression(expression)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("Failed to parse expression: {}. Consider using the Python parser for complex expressions.", e)
                ))?
        };
        
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

/// Convert Python AST dictionary to Rust ExprNode.
fn dict_to_expr_node(py: Python, dict: &Bound<'_, PyDict>) -> PyResult<ExprNode> {
    let node_type = dict.get_item("type")?
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'type' field"))?
        .extract::<String>()?;
    
    match node_type.as_str() {
        "Feature" => {
            let name = dict.get_item("name")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'name' field"))?
                .extract::<String>()?;
            Ok(ExprNode::Feature(name))
        },
        "Constant" => {
            let value = dict.get_item("value")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'value' field"))?
                .extract::<f64>()?;
            Ok(ExprNode::Constant(value))
        },
        "Operator" => {
            let name = dict.get_item("name")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'name' field"))?
                .extract::<String>()?;
            
            // Parse arguments
            let args_list = dict.get_item("args")?
                .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("Missing 'args' field"))?
                .downcast::<PyList>()
                .map_err(|_| PyErr::new::<pyo3::exceptions::PyTypeError, _>("'args' must be a list"))?;
            
            let mut args = Vec::new();
            for arg in args_list.iter() {
                let arg_dict = arg.downcast::<PyDict>()
                    .map_err(|_| PyErr::new::<pyo3::exceptions::PyTypeError, _>("Argument must be a dictionary"))?;
                let node = dict_to_expr_node(py, &arg_dict)?;
                args.push(CompiledExpression::new(node));
            }
            
            // Parse parameters
            let mut params = HashMap::new();
            if let Some(params_dict) = dict.get_item("params")? {
                let params_dict = params_dict.downcast::<PyDict>()
                    .map_err(|_| PyErr::new::<pyo3::exceptions::PyTypeError, _>("'params' must be a dictionary"))?;
                for (key, value) in params_dict.iter() {
                    let key = key.extract::<String>()?;
                    let value = value.extract::<f64>()?;
                    params.insert(key, value);
                }
            }
            
            Ok(ExprNode::Operator { name, args, params })
        },
        _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Unknown node type: {}", node_type)
        ))
    }
}

/// Serialize ExprNode back to Python dictionary.
fn serialize_expr_node(py: Python, node: &ExprNode) -> PyResult<PyObject> {
    let dict = PyDict::new(py);
    
    match node {
        ExprNode::Feature(name) => {
            dict.set_item("type", "Feature")?;
            dict.set_item("name", name)?;
        },
        ExprNode::Constant(value) => {
            dict.set_item("type", "Constant")?;
            dict.set_item("value", value)?;
        },
        ExprNode::Operator { name, args, params } => {
            dict.set_item("type", "Operator")?;
            dict.set_item("name", name)?;
            
            // Serialize arguments
            let args_list = PyList::empty(py);
            for arg in args {
                let arg_dict = serialize_expr_node(py, &arg.node)?;
                args_list.append(arg_dict)?;
            }
            dict.set_item("args", &args_list)?;
            
            // Serialize parameters
            let params_dict = PyDict::new(py);
            for (key, value) in params {
                params_dict.set_item(key, value)?;
            }
            dict.set_item("params", &params_dict)?;
        }
    }
    
    Ok(dict.into_any().unbind())

/// Factory function to create and compile expressions from Python.
#[pyfunction]
#[pyo3(signature = (ast_dict))]
pub fn compile_expression_from_python(
    py: Python,
    ast_dict: &Bound<'_, PyDict>,
) -> PyResult<PyObject> {
    // Convert Python AST dictionary to Rust ExprNode
    let node = dict_to_expr_node(py, ast_dict)?;
    
    // Create CompiledExpression
    let compiled = CompiledExpression::new(node);
    
    // Convert back to Python dict for serialization
    let result = PyDict::new(py);
    
    // Serialize the expression tree
    let node_dict = serialize_expr_node(py, &compiled.node)?;
    result.set_item("node", node_dict)?;
    
    // Add metadata
    let metadata_dict = PyDict::new(py);
    metadata_dict.set_item("features", compiled.metadata.features.clone())?;
    metadata_dict.set_item("max_window", compiled.metadata.max_window)?;
    metadata_dict.set_item("has_cross_sectional", compiled.metadata.has_cross_sectional)?;
    metadata_dict.set_item("operators", compiled.metadata.operators.clone())?;
    metadata_dict.set_item("complexity", compiled.metadata.complexity)?;
    result.set_item("metadata", &metadata_dict)?;
    
    Ok(result.into_any().unbind())
}