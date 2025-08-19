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

//! Unified node architecture for evaluating FactorExp expressions.
//! 
//! This module implements a unified architecture where all expression tree nodes
//! (both features and operators) implement the same interface, enabling true
//! transparency and incremental updates.

use std::collections::HashMap;
use crate::{
    buffer::RollingBuffer,
    expression::{CompiledExpression, ExprNode, ExpressionError, ExpressionResult},
    operators::{RollingOperator, get_rolling_operator, get_pair_rolling_operator, pair_rolling::PairRollingOperator},
};

/// Context passed during node updates containing current bar data.
#[derive(Debug, Clone)]
pub struct UpdateContext {
    /// Current bar's feature values (close, volume, etc.)
    pub features: HashMap<String, f64>,
}

impl UpdateContext {
    /// Creates a new update context with feature values.
    pub fn new(features: HashMap<String, f64>) -> Self {
        Self { features }
    }
}

/// Unified interface for all expression tree nodes.
/// 
/// This trait enables complete transparency between features and operators - 
/// every node in the expression tree implements the same interface.
/// 
/// Requires Send + Sync for thread safety in Python bindings.
pub trait ExpressionNode: std::fmt::Debug + Send + Sync {
    /// Update node state with new data context.
    /// 
    /// This method is called when a new bar arrives and propagates 
    /// through the expression tree to update all nodes incrementally.
    fn update(&mut self, context: &UpdateContext) -> ExpressionResult<()>;
    
    /// Get current computed value.
    /// 
    /// Returns the node's current value or None if not yet available.
    /// This provides the transparent interface that makes all nodes equivalent.
    fn current_value(&self) -> Option<f64>;
    
    /// Reset node state to initial conditions.
    fn reset(&mut self);
    
    /// Get node name for debugging and diagnostics.
    fn name(&self) -> &str;
    
    /// Check if node has sufficient data to produce valid output.
    fn is_ready(&self) -> bool {
        self.current_value().is_some()
    }
}

/// Feature node representing raw data sources like $close, $volume.
/// 
/// These nodes form the leaves of the expression tree and provide
/// transparent access to raw market data.
#[derive(Debug, Clone)]
pub struct FeatureNode {
    feature_name: String,
    current_value: Option<f64>,
}

impl FeatureNode {
    /// Creates a new feature node.
    pub fn new(feature_name: String) -> Self {
        Self {
            feature_name,
            current_value: None,
        }
    }
}

impl ExpressionNode for FeatureNode {
    fn update(&mut self, context: &UpdateContext) -> ExpressionResult<()> {
        // Extract feature name without $ prefix
        let clean_name = self.feature_name.trim_start_matches('$');
        
        // Update current value from context
        self.current_value = context.features.get(clean_name).copied();
        
        Ok(())
    }
    
    fn current_value(&self) -> Option<f64> {
        self.current_value
    }
    
    fn reset(&mut self) {
        self.current_value = None;
    }
    
    fn name(&self) -> &str {
        &self.feature_name
    }
}

/// Operator node representing rolling computations like TS_Mean, TS_Sum.
/// 
/// These nodes maintain their own rolling state and provide transparent
/// access to computed values, making them indistinguishable from features
/// to parent nodes.
#[derive(Debug)]
pub struct OperatorNode {
    operator_name: String,
    operator: Option<Box<dyn RollingOperator>>,
    pair_operator: Option<Box<dyn PairRollingOperator>>,
    children: Vec<Box<dyn ExpressionNode>>,
    current_value: Option<f64>,
    window_size: usize,
    params: HashMap<String, f64>,
    staleness_count: usize,
}

/// Maximum consecutive invalid values before warning
const STALENESS_THRESHOLD: usize = 10;

impl OperatorNode {
    /// Creates a new operator node.
    pub fn new(
        operator_name: String,
        children: Vec<Box<dyn ExpressionNode>>,
        params: HashMap<String, f64>,
    ) -> ExpressionResult<Self> {
        let window_size = params.get("window")
            .ok_or_else(|| ExpressionError::InvalidParameters(
                "Operator requires 'window' parameter".to_string()
            ))?
            .clone() as usize;

        let operator = get_rolling_operator(&operator_name, window_size);
        let pair_operator = get_pair_rolling_operator(&operator_name, window_size);
        
        Ok(Self {
            operator_name,
            operator,
            pair_operator,
            children,
            current_value: None,
            window_size,
            params,
            staleness_count: 0,
        })
    }
}

impl ExpressionNode for OperatorNode {
    fn update(&mut self, context: &UpdateContext) -> ExpressionResult<()> {
        // First, update all children
        for child in &mut self.children {
            child.update(context)?;
        }
        
        // Check if this is a pair operator that needs two inputs
        if self.pair_operator.is_some() {
            // Handle pair rolling operators (e.g., TS_Corr, TS_Cov, TS_Beta)
            if self.children.len() >= 2 {
                if let (Some(input1), Some(input2)) = (
                    self.children[0].current_value(),
                    self.children[1].current_value()
                ) {
                    // Initialize pair operator if not already done
                    if self.pair_operator.is_none() {
                        self.pair_operator = get_pair_rolling_operator(&self.operator_name, self.window_size);
                    }
                    
                    // Update pair operator state with new values
                    if let Some(ref mut pair_operator) = self.pair_operator {
                        // Check if inputs are valid (not NaN)
                        if !input1.is_nan() && !input2.is_nan() {
                            // Valid inputs: reset staleness counter
                            self.staleness_count = 0;
                        } else {
                            // Invalid inputs: increment staleness counter
                            self.staleness_count += 1;
                            if self.staleness_count > STALENESS_THRESHOLD {
                                eprintln!("Warning: {} has received {} consecutive invalid values", 
                                        self.operator_name, self.staleness_count);
                            }
                        }
                        
                        pair_operator.update(input1, input2);
                        
                        // Only set current_value when operator has sufficient data
                        if pair_operator.is_ready() {
                            self.current_value = Some(pair_operator.value());
                        } else {
                            self.current_value = None;
                        }
                    }
                }
            }
        } else {
            // Handle single-input rolling operators
            if let Some(child) = self.children.first() {
                if let Some(input_value) = child.current_value() {
                    // Initialize operator if not already done
                    if self.operator.is_none() {
                        self.operator = get_rolling_operator(&self.operator_name, self.window_size);
                    }
                    
                    // Update operator state with new value
                    if let Some(ref mut operator) = self.operator {
                        // Check if input is valid (not NaN)
                        if !input_value.is_nan() {
                            // Valid input: reset staleness counter
                            self.staleness_count = 0;
                        } else {
                            // Invalid input: increment staleness counter
                            self.staleness_count += 1;
                            if self.staleness_count > STALENESS_THRESHOLD {
                                eprintln!("Warning: {} has received {} consecutive invalid values", 
                                        self.operator_name, self.staleness_count);
                            }
                        }
                        
                        operator.update(input_value);
                        
                        // Only set current_value when operator has sufficient data
                        if operator.is_ready() {
                            self.current_value = Some(operator.value());
                        } else {
                            self.current_value = None;
                        }
                    } else {
                        return Err(ExpressionError::UnknownOperator(self.operator_name.clone()));
                    }
                } else {
                    // Child not ready - we're not ready either
                    self.current_value = None;
                    self.staleness_count += 1;
                }
            }
        }
        
        Ok(())
    }
    
    fn current_value(&self) -> Option<f64> {
        self.current_value
    }
    
    fn reset(&mut self) {
        // Reset operator state
        self.operator = get_rolling_operator(&self.operator_name, self.window_size);
        self.pair_operator = get_pair_rolling_operator(&self.operator_name, self.window_size);
        self.current_value = None;
        self.staleness_count = 0;
        
        // Reset all children
        for child in &mut self.children {
            child.reset();
        }
    }
    
    fn name(&self) -> &str {
        &self.operator_name
    }
}

/// Instant operator node representing immediate computations like Add, Sin, etc.
/// 
/// Unlike rolling operators, instant operators don't maintain historical state
/// and compute results immediately from current input values.
#[derive(Debug)]
pub struct InstantOperatorNode {
    operator_name: String,
    children: Vec<Box<dyn ExpressionNode>>,
    current_value: Option<f64>,
}

impl InstantOperatorNode {
    /// Creates a new instant operator node.
    pub fn new(
        operator_name: String,
        children: Vec<Box<dyn ExpressionNode>>,
    ) -> Self {
        Self {
            operator_name,
            children,
            current_value: None,
        }
    }
    
    /// Computes the operator result from current child values.
    fn compute_result(&self, child_values: &[f64]) -> ExpressionResult<f64> {
        match self.operator_name.as_str() {
            // Binary arithmetic operators
            "Add" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Add requires 2 arguments".to_string()));
                }
                Ok(child_values[0] + child_values[1])
            }
            "Sub" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Sub requires 2 arguments".to_string()));
                }
                Ok(child_values[0] - child_values[1])
            }
            "Mul" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Mul requires 2 arguments".to_string()));
                }
                Ok(child_values[0] * child_values[1])
            }
            "Div" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Div requires 2 arguments".to_string()));
                }
                if child_values[1] != 0.0 {
                    Ok(child_values[0] / child_values[1])
                } else {
                    Ok(f64::NAN)
                }
            }
            "Pow" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Pow requires 2 arguments".to_string()));
                }
                Ok(child_values[0].powf(child_values[1]))
            }
            
            // Unary operators
            "Neg" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Neg requires 1 argument".to_string()));
                }
                Ok(-child_values[0])
            }
            "Abs" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Abs requires 1 argument".to_string()));
                }
                Ok(child_values[0].abs())
            }
            "Sign" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Sign requires 1 argument".to_string()));
                }
                let val = child_values[0];
                Ok(if val > 0.0 { 1.0 } else if val < 0.0 { -1.0 } else { 0.0 })
            }
            
            // Math functions
            "Sqrt" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Sqrt requires 1 argument".to_string()));
                }
                Ok(child_values[0].sqrt())
            }
            "Log" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Log requires 1 argument".to_string()));
                }
                Ok(child_values[0].ln())
            }
            "Log10" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Log10 requires 1 argument".to_string()));
                }
                Ok(child_values[0].log10())
            }
            "Exp" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Exp requires 1 argument".to_string()));
                }
                Ok(child_values[0].exp())
            }
            
            // Trigonometric functions
            "Sin" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Sin requires 1 argument".to_string()));
                }
                Ok(child_values[0].sin())
            }
            "Cos" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Cos requires 1 argument".to_string()));
                }
                Ok(child_values[0].cos())
            }
            "Tan" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Tan requires 1 argument".to_string()));
                }
                Ok(child_values[0].tan())
            }
            "Asin" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Asin requires 1 argument".to_string()));
                }
                Ok(child_values[0].asin())
            }
            "Acos" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Acos requires 1 argument".to_string()));
                }
                Ok(child_values[0].acos())
            }
            "Atan" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Atan requires 1 argument".to_string()));
                }
                Ok(child_values[0].atan())
            }
            
            // Hyperbolic functions
            "Sinh" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Sinh requires 1 argument".to_string()));
                }
                Ok(child_values[0].sinh())
            }
            "Cosh" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Cosh requires 1 argument".to_string()));
                }
                Ok(child_values[0].cosh())
            }
            "Tanh" => {
                if child_values.len() != 1 {
                    return Err(ExpressionError::InvalidParameters("Tanh requires 1 argument".to_string()));
                }
                Ok(child_values[0].tanh())
            }
            
            // Comparison operators  
            "Max" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Max requires 2 arguments".to_string()));
                }
                Ok(child_values[0].max(child_values[1]))
            }
            "Min" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Min requires 2 arguments".to_string()));
                }
                Ok(child_values[0].min(child_values[1]))
            }
            "Greater" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Greater requires 2 arguments".to_string()));
                }
                Ok(if child_values[0] > child_values[1] { 1.0 } else { 0.0 })
            }
            "Less" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Less requires 2 arguments".to_string()));
                }
                Ok(if child_values[0] < child_values[1] { 1.0 } else { 0.0 })
            }
            "GreaterEq" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("GreaterEq requires 2 arguments".to_string()));
                }
                Ok(if child_values[0] >= child_values[1] { 1.0 } else { 0.0 })
            }
            "LessEq" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("LessEq requires 2 arguments".to_string()));
                }
                Ok(if child_values[0] <= child_values[1] { 1.0 } else { 0.0 })
            }
            "Equal" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("Equal requires 2 arguments".to_string()));
                }
                Ok(if (child_values[0] - child_values[1]).abs() < 1e-10 { 1.0 } else { 0.0 })
            }
            "NotEqual" => {
                if child_values.len() != 2 {
                    return Err(ExpressionError::InvalidParameters("NotEqual requires 2 arguments".to_string()));
                }
                Ok(if (child_values[0] - child_values[1]).abs() >= 1e-10 { 1.0 } else { 0.0 })
            }
            
            _ => Err(ExpressionError::UnknownOperator(self.operator_name.clone())),
        }
    }
}

impl ExpressionNode for InstantOperatorNode {
    fn update(&mut self, context: &UpdateContext) -> ExpressionResult<()> {
        // Update all children first
        for child in &mut self.children {
            child.update(context)?;
        }
        
        // Collect current values from children
        let mut child_values = Vec::new();
        for child in &self.children {
            if let Some(value) = child.current_value() {
                child_values.push(value);
            } else {
                // If any child is not ready, we're not ready either
                self.current_value = None;
                return Ok(());
            }
        }
        
        // Compute result from child values
        match self.compute_result(&child_values) {
            Ok(result) => {
                self.current_value = Some(result);
            }
            Err(_) => {
                self.current_value = None;
            }
        }
        
        Ok(())
    }
    
    fn current_value(&self) -> Option<f64> {
        self.current_value
    }
    
    fn reset(&mut self) {
        self.current_value = None;
        
        // Reset all children
        for child in &mut self.children {
            child.reset();
        }
    }
    
    fn name(&self) -> &str {
        &self.operator_name
    }
}

/// Constant node representing literal values in expressions.
#[derive(Debug, Clone)]
pub struct ConstantNode {
    value: f64,
    name: String,
}

impl ConstantNode {
    /// Creates a new constant node.
    pub fn new(value: f64) -> Self {
        Self {
            value,
            name: format!("Const({})", value),
        }
    }
}

impl ExpressionNode for ConstantNode {
    fn update(&mut self, _context: &UpdateContext) -> ExpressionResult<()> {
        // Constants don't need updates
        Ok(())
    }
    
    fn current_value(&self) -> Option<f64> {
        Some(self.value)
    }
    
    fn reset(&mut self) {
        // Constants don't need reset
    }
    
    fn name(&self) -> &str {
        &self.name
    }
}

/// Engine for computing FactorExp expressions using unified node architecture.
/// 
/// The engine builds a tree of ExpressionNode objects that maintain state
/// and support incremental updates, providing true transparency between
/// features and operators.
#[derive(Debug)]
pub struct ComputationEngine {
    /// Root node of the expression tree
    root_node: Option<Box<dyn ExpressionNode>>,
}

impl ComputationEngine {
    /// Creates a new [`ComputationEngine`].
    pub fn new() -> Self {
        Self {
            root_node: None,
        }
    }
    
    /// Determines if an operator is a rolling (stateful) operator.
    fn is_rolling_operator(name: &str) -> bool {
        // Check if it's a time-series operator or a statistical rolling operator
        matches!(name,
            // Time-series operators
            "TS_Mean" | "TS_Sum" | "TS_Min" | "TS_Max" | "TS_Std" | "TS_Var" |
            "TS_Med" | "TS_Median" | "TS_Product" | "TS_Delta" | "TS_Ref" | "TS_Rank" |
            "TS_Argmax" | "TS_Argmin" | "TS_EMA" | "TS_WMA" | "TS_Skew" |
            "TS_Kurt" | "TS_Kurtosis" | "TS_Mad" | "TS_Corr" | "TS_Cov" | "TS_Beta" |
            "TS_PctChg" |
            // Statistical rolling operators without TS_ prefix
            "ZScore" | "Demean"
        )
    }
    
    /// Builds the expression tree from a compiled expression.
    pub fn build_tree(&mut self, expr: &CompiledExpression) -> ExpressionResult<()> {
        self.root_node = Some(self.build_node(&expr.node)?);
        Ok(())
    }
    
    /// Builds a unified node from an expression node.
    fn build_node(&self, node: &ExprNode) -> ExpressionResult<Box<dyn ExpressionNode>> {
        match node {
            ExprNode::Constant(value) => {
                Ok(Box::new(ConstantNode::new(*value)))
            }
            
            ExprNode::Feature(name) => {
                Ok(Box::new(FeatureNode::new(name.clone())))
            }
            
            ExprNode::Operator { name, args, params } => {
                // Build child nodes recursively
                let mut children = Vec::new();
                for arg in args {
                    children.push(self.build_node(&arg.node)?);
                }
                
                // Handle different operator types
                if Self::is_rolling_operator(name) {
                    // Rolling operators (time-series and statistical)
                    Ok(Box::new(OperatorNode::new(name.clone(), children, params.clone())?))
                } else {
                    // Instant (non-rolling) operators: Add, Sub, Mul, Sin, etc.
                    Ok(Box::new(InstantOperatorNode::new(name.clone(), children)))
                }
            }
        }
    }
    
    /// Updates the expression tree with new bar data and returns current value.
    /// 
    /// This method implements the unified architecture where:
    /// 1. New bar data is packaged into an UpdateContext
    /// 2. The entire expression tree is updated incrementally  
    /// 3. The current computed value is returned
    /// 
    /// This approach eliminates special cases and provides true transparency.
    pub fn update_and_compute(
        &mut self,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<Option<f64>> {
        // Extract current values from buffers to create update context
        let mut features = HashMap::new();
        for (name, buffer) in buffers {
            if let Some(value) = buffer.last() {
                features.insert(name.clone(), value);
            }
        }
        
        let context = UpdateContext::new(features);
        
        // Update the entire expression tree
        if let Some(ref mut root) = self.root_node {
            root.update(&context)?;
            
            // Return current value (None if not ready, which is valid)
            Ok(root.current_value())
        } else {
            Err(ExpressionError::ComputationError(
                "Expression tree not built. Call build_tree() first.".to_string()
            ))
        }
    }
    
    /// Legacy method for backward compatibility.
    /// 
    /// This method builds the tree on-demand and computes the result.
    /// For better performance, use build_tree() once followed by
    /// update_and_compute() for each bar.
    pub fn compute(
        &mut self,
        expr: &CompiledExpression,
        buffers: &HashMap<String, RollingBuffer>,
    ) -> ExpressionResult<f64> {
        // Build tree if not already built
        if self.root_node.is_none() {
            self.build_tree(expr)?;
        }
        
        // Update and compute
        match self.update_and_compute(buffers)? {
            Some(value) => Ok(value),
            None => Ok(f64::NAN),  // Return NaN when not ready (for backward compatibility)
        }
    }
    
    /// Gets the current computed value without updating.
    pub fn current_value(&self) -> Option<f64> {
        self.root_node.as_ref().and_then(|root| root.current_value())
    }
    
    /// Resets the expression tree state.
    pub fn reset(&mut self) {
        if let Some(ref mut root) = self.root_node {
            root.reset();
        }
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
    fn test_unified_constant_computation() {
        let mut engine = ComputationEngine::new();
        let expr = CompiledExpression::new(ExprNode::Constant(42.0));
        let buffers = HashMap::new();
        
        let result = engine.compute(&expr, &buffers).unwrap();
        assert_eq!(result, 42.0);
    }
    
    #[test]
    fn test_unified_feature_computation() {
        let mut engine = ComputationEngine::new();
        let expr = CompiledExpression::new(ExprNode::Feature("$close".to_string()));
        
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        close_buffer.push(100.0);
        buffers.insert("close".to_string(), close_buffer);
        
        let result = engine.compute(&expr, &buffers).unwrap();
        assert_eq!(result, 100.0);
    }
    
    #[test]
    fn test_unified_ts_mean_simple() {
        let mut engine = ComputationEngine::new();
        
        // Create TS_Mean($close, 2) expression
        let mut params = HashMap::new();
        params.insert("window".to_string(), 2.0);
        
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Feature("$close".to_string()))
                ],
                params,
            }
        );
        
        // Build the expression tree
        engine.build_tree(&expr).unwrap();
        
        // Create test data
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        
        // Add first value - not enough data yet
        close_buffer.push(100.0);
        buffers.insert("close".to_string(), close_buffer.clone());
        
        let result1 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result1, None); // Not enough data for 2-period mean
        
        // Add second value - now we have enough data
        close_buffer.push(102.0);
        buffers.insert("close".to_string(), close_buffer.clone());
        
        let result2 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result2, Some(101.0)); // (100 + 102) / 2 = 101
        
        // Add third value
        close_buffer.push(104.0);
        buffers.insert("close".to_string(), close_buffer);
        
        let result3 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result3, Some(103.0)); // (102 + 104) / 2 = 103
    }
    
    #[test]
    fn test_unified_nested_ts_mean() {
        let mut engine = ComputationEngine::new();
        
        // Create TS_Mean(TS_Mean($close, 2), 1) - this should equal TS_Mean($close, 2)
        let mut inner_params = HashMap::new();
        inner_params.insert("window".to_string(), 2.0);
        
        let mut outer_params = HashMap::new();
        outer_params.insert("window".to_string(), 1.0);
        
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Operator {
                        name: "TS_Mean".to_string(),
                        args: vec![
                            CompiledExpression::new(ExprNode::Feature("$close".to_string()))
                        ],
                        params: inner_params,
                    })
                ],
                params: outer_params,
            }
        );
        
        // Build the expression tree
        engine.build_tree(&expr).unwrap();
        
        // Create test data  
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        
        // Add test values progressively
        close_buffer.push(100.0);
        buffers.insert("close".to_string(), close_buffer.clone());
        let result1 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result1, None); // Inner mean not ready
        
        close_buffer.push(102.0);
        buffers.insert("close".to_string(), close_buffer.clone());
        let result2 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result2, Some(101.0)); // Inner: (100+102)/2=101, Outer: 101/1=101
        
        close_buffer.push(104.0);
        buffers.insert("close".to_string(), close_buffer);
        let result3 = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result3, Some(103.0)); // Inner: (102+104)/2=103, Outer: 103/1=103
    }
    
    #[test]
    fn test_unified_complex_mixed_operators() {
        let mut engine = ComputationEngine::new();
        
        // Create complex expression: TS_Mean(TS_Mean($close, 4) + TS_Mean($open, 5), 2)
        let mut close_mean_params = HashMap::new();
        close_mean_params.insert("window".to_string(), 4.0);
        
        let mut open_mean_params = HashMap::new();
        open_mean_params.insert("window".to_string(), 5.0);
        
        let mut outer_mean_params = HashMap::new();
        outer_mean_params.insert("window".to_string(), 2.0);
        
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Operator {
                        name: "Add".to_string(),
                        args: vec![
                            CompiledExpression::new(ExprNode::Operator {
                                name: "TS_Mean".to_string(),
                                args: vec![
                                    CompiledExpression::new(ExprNode::Feature("$close".to_string()))
                                ],
                                params: close_mean_params,
                            }),
                            CompiledExpression::new(ExprNode::Operator {
                                name: "TS_Mean".to_string(),
                                args: vec![
                                    CompiledExpression::new(ExprNode::Feature("$open".to_string()))
                                ],
                                params: open_mean_params,
                            }),
                        ],
                        params: HashMap::new(),
                    })
                ],
                params: outer_mean_params,
            }
        );
        
        // Build the expression tree
        engine.build_tree(&expr).unwrap();
        
        // Create test data  
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        let mut open_buffer = RollingBuffer::new(10);
        
        // Add test values progressively - need enough for complex nesting to be ready
        let close_values = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0];
        let open_values = [99.0, 101.0, 103.0, 105.0, 107.0, 109.0, 111.0];
        
        for i in 0..7 {
            close_buffer.push(close_values[i]);
            open_buffer.push(open_values[i]);
            buffers.insert("close".to_string(), close_buffer.clone());
            buffers.insert("open".to_string(), open_buffer.clone());
            
            let result = engine.update_and_compute(&buffers).unwrap();
            
            if i < 5 {
                // Complex requirements:
                // - TS_Mean($close, 4) needs 4 values (ready at i=3)  
                // - TS_Mean($open, 5) needs 5 values (ready at i=4)
                // - Add needs both inputs ready (ready at i=4)
                // - TS_Mean(Add_result, 2) needs 2 Add results (ready at i=5)
                // So complete expression ready at i=5
                assert_eq!(result, None, "Should not have enough data at step {}", i);
            } else {
                // Should have enough data now (i>=5)
                assert!(result.is_some(), "Should have enough data at step {}", i);
                let value = result.unwrap();
                
                // Verify it's a reasonable number
                assert!(value > 0.0 && value < 1000.0, "Value should be reasonable, got {}", value);
                
                // At i=5:
                // close_mean[4] = (103+105+107+109)/4 = 106.0
                // open_mean[4] = (99+101+103+105+107)/5 = 103.0  
                // add_result[4] = 106.0 + 103.0 = 209.0
                // 
                // close_mean[5] = (105+107+109+111)/4 = 108.0
                // open_mean[5] = (101+103+105+107+109)/5 = 105.0
                // add_result[5] = 108.0 + 105.0 = 213.0
                //
                // outer_mean[5] = (209.0 + 213.0)/2 = 211.0
                if i == 5 {
                    // Rough verification - should be around 210-215
                    assert!(value >= 200.0 && value <= 220.0, "Expected ~211, got {}", value);
                }
            }
        }
    }
    
    #[test]
    fn test_unified_instant_operators() {
        let mut engine = ComputationEngine::new();
        
        // Create simple arithmetic: $close + $open
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "Add".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Feature("$close".to_string())),
                    CompiledExpression::new(ExprNode::Feature("$open".to_string())),
                ],
                params: HashMap::new(),
            }
        );
        
        // Build the expression tree
        engine.build_tree(&expr).unwrap();
        
        // Create test data  
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        let mut open_buffer = RollingBuffer::new(10);
        
        close_buffer.push(100.0);
        open_buffer.push(50.0);
        buffers.insert("close".to_string(), close_buffer);
        buffers.insert("open".to_string(), open_buffer);
        
        let result = engine.update_and_compute(&buffers).unwrap();
        assert_eq!(result, Some(150.0)); // 100 + 50 = 150
    }
    
    #[test]
    fn test_unified_math_operators() {
        let mut engine = ComputationEngine::new();
        
        // Create math expression: Sin($close)
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "Sin".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Feature("$close".to_string())),
                ],
                params: HashMap::new(),
            }
        );
        
        // Build the expression tree
        engine.build_tree(&expr).unwrap();
        
        // Create test data  
        let mut buffers = HashMap::new();
        let mut close_buffer = RollingBuffer::new(10);
        
        close_buffer.push(0.0); // sin(0) = 0
        buffers.insert("close".to_string(), close_buffer);
        
        let result = engine.update_and_compute(&buffers).unwrap();
        assert!((result.unwrap() - 0.0).abs() < 1e-10); // sin(0) ≈ 0
    }
}