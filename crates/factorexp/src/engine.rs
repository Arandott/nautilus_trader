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

//! Computation engine for evaluating FactorExp expressions.

use std::collections::HashMap;
use crate::{
    buffer::RollingBuffer,
    expression::{CompiledExpression, ExprNode, ExpressionError, ExpressionResult},
    operators::{RollingOperator, get_rolling_operator},
};

/// Engine for computing FactorExp expressions.
#[derive(Debug)]
pub struct ComputationEngine {
    /// Cache for computed values.
    cache: HashMap<String, f64>,
    /// Operators for computation.
    operators: HashMap<String, Box<dyn RollingOperator>>,
}

impl ComputationEngine {
    /// Creates a new [`ComputationEngine`].
    pub fn new() -> Self {
        Self {
            cache: HashMap::new(),
            operators: HashMap::new(),
        }
    }
    
    /// Computes the value of an expression.
    pub fn compute(
        &mut self,
        expr: &CompiledExpression,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<f64> {
        self.compute_node(&expr.node, buffers)
    }
    
    /// Computes the value of an expression node.
    fn compute_node(
        &mut self,
        node: &ExprNode,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<f64> {
        match node {
            ExprNode::Constant(val) => Ok(*val),
            
            ExprNode::Feature(name) => {
                // Handle feature references (e.g., $close, $volume)
                let feature_name = name.trim_start_matches('$');
                
                buffers.get(feature_name)
                    .and_then(|b| b.last())
                    .ok_or_else(|| ExpressionError::ComputationError(
                        format!("Feature '{}' not found or empty", feature_name)
                    ))
            }
            
            ExprNode::Operator { name, args, params } => {
                self.compute_operator(name, args, params, buffers)
            }
        }
    }
    
    /// Computes an operator.
    fn compute_operator(
        &mut self,
        name: &str,
        args: &[CompiledExpression],
        params: &HashMap<String, f64>,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<f64> {
        match name {
            // Basic arithmetic operators
            "Add" => self.compute_binary_op(args, buffers, |a, b| a + b),
            "Sub" => self.compute_binary_op(args, buffers, |a, b| a - b),
            "Mul" => self.compute_binary_op(args, buffers, |a, b| a * b),
            "Div" => self.compute_binary_op(args, buffers, |a, b| {
                if b != 0.0 { a / b } else { f64::NAN }
            }),
            "Pow" => self.compute_binary_op(args, buffers, |a, b| a.powf(b)),
            
            // Unary operators
            "Neg" => self.compute_unary_op(args, buffers, |a| -a),
            "Abs" => self.compute_unary_op(args, buffers, |a| a.abs()),
            "Sqrt" => self.compute_unary_op(args, buffers, |a| a.sqrt()),
            "Log" => self.compute_unary_op(args, buffers, |a| a.ln()),
            
            // Comparison operators
            "Max" => self.compute_binary_op(args, buffers, |a, b| a.max(b)),
            "Min" => self.compute_binary_op(args, buffers, |a, b| a.min(b)),
            
            // Time-series operators
            name if name.starts_with("TS_") => {
                self.compute_ts_operator(name, args, params, buffers)
            }
            
            // Cross-sectional operators (placeholder for future)
            name if name.starts_with("CS_") => {
                Err(ExpressionError::UnknownOperator(
                    format!("Cross-sectional operator '{}' not yet implemented", name)
                ))
            }
            
            _ => Err(ExpressionError::UnknownOperator(name.to_string())),
        }
    }
    
    /// Computes a binary operator.
    fn compute_binary_op<F>(
        &mut self,
        args: &[CompiledExpression],
        buffers: &HashMap<String, RollingBuffer>,
        op: F,
    ) -> ExpressionResult<f64>
    where
        F: Fn(f64, f64) -> f64,
    {
        if args.len() != 2 {
            return Err(ExpressionError::InvalidParameters(
                "Binary operator requires exactly 2 arguments".to_string()
            ));
        }
        
        let a = self.compute_node(&args[0].node, buffers)?;
        let b = self.compute_node(&args[1].node, buffers)?;
        
        Ok(op(a, b))
    }
    
    /// Computes a unary operator.
    fn compute_unary_op<F>(
        &mut self,
        args: &[CompiledExpression],
        buffers: &HashMap<String, RollingBuffer>,
        op: F,
    ) -> ExpressionResult<f64>
    where
        F: Fn(f64) -> f64,
    {
        if args.len() != 1 {
            return Err(ExpressionError::InvalidParameters(
                "Unary operator requires exactly 1 argument".to_string()
            ));
        }
        
        let a = self.compute_node(&args[0].node, buffers)?;
        Ok(op(a))
    }
    
    /// Computes a time-series operator.
    fn compute_ts_operator(
        &mut self,
        name: &str,
        args: &[CompiledExpression],
        params: &HashMap<String, f64>,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<f64> {
        // Get window size
        let window = *params.get("window")
            .ok_or_else(|| ExpressionError::InvalidParameters(
                "Time-series operator requires 'window' parameter".to_string()
            ))? as usize;
        
        // For now, we'll compute on the feature buffer directly
        // In a full implementation, we'd handle arbitrary expressions
        if args.len() != 1 {
            return Err(ExpressionError::InvalidParameters(
                "Time-series operator requires exactly 1 argument".to_string()
            ));
        }
        
        // Extract feature name if the argument is a feature
        if let ExprNode::Feature(feature_name) = &args[0].node {
            let clean_name = feature_name.trim_start_matches('$');
            
            let buffer = buffers.get(clean_name)
                .ok_or_else(|| ExpressionError::ComputationError(
                    format!("Feature '{}' not found", clean_name)
                ))?;
            
            // Create or get operator
            let op_key = format!("{}_{}", name, window);
            if !self.operators.contains_key(&op_key) {
                let operator = get_rolling_operator(name, window)
                    .ok_or_else(|| ExpressionError::UnknownOperator(name.to_string()))?;
                self.operators.insert(op_key.clone(), operator);
            }
            
            // Update operator with buffer values and return result
            let operator = self.operators.get_mut(&op_key).unwrap();
            
            // Update with all values in buffer
            operator.reset();
            for value in buffer.values() {
                operator.update(value);
            }
            
            Ok(operator.value())
        } else {
            // For complex expressions as arguments, we'd need more sophisticated handling
            Err(ExpressionError::InvalidParameters(
                "Time-series operators currently only support feature arguments".to_string()
            ))
        }
    }
    
    /// Resets the engine state.
    pub fn reset(&mut self) {
        self.cache.clear();
        self.operators.clear();
    }
}

impl Default for ComputationEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::expression::CompiledExpression;
    
    #[test]
    fn test_constant_computation() {
        let mut engine = ComputationEngine::new();
        let expr = CompiledExpression::new(ExprNode::Constant(42.0));
        let buffers = HashMap::new();
        
        let result = engine.compute(&expr, &buffers).unwrap();
        assert_eq!(result, 42.0);
    }
    
    #[test]
    fn test_arithmetic_computation() {
        let mut engine = ComputationEngine::new();
        
        // Create expression: 10 + 5
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "Add".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Constant(10.0)),
                    CompiledExpression::new(ExprNode::Constant(5.0)),
                ],
                params: HashMap::new(),
            }
        );
        
        let buffers = HashMap::new();
        let result = engine.compute(&expr, &buffers).unwrap();
        assert_eq!(result, 15.0);
    }
    
    #[test]
    fn test_feature_computation() {
        let mut engine = ComputationEngine::new();
        let expr = CompiledExpression::new(ExprNode::Feature("$close".to_string()));
        
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        close_buffer.push(100.0);
        buffers.insert("close".to_string(), close_buffer);
        
        let result = engine.compute(&expr, &buffers).unwrap();
        assert_eq!(result, 100.0);
    }
}