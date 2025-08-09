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

//! Expression data structures for FactorExp.

use std::collections::HashMap;
use serde::{Serialize, Deserialize};

/// Represents a node in the compiled expression tree.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ExprNode {
    /// A constant value.
    Constant(f64),
    
    /// A feature reference (e.g., $close, $volume).
    Feature(String),
    
    /// An operator with arguments and parameters.
    Operator {
        /// The operator name (e.g., "TS_Mean", "Add").
        name: String,
        /// The arguments to the operator.
        args: Vec<CompiledExpression>,
        /// Parameters for the operator (e.g., window size).
        params: HashMap<String, f64>,
    },
}

/// A compiled expression ready for evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledExpression {
    /// The expression tree node.
    pub node: ExprNode,
    /// Metadata about the expression.
    pub metadata: ExpressionMetadata,
}

/// Metadata about an expression.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExpressionMetadata {
    /// List of features used in the expression.
    pub features: Vec<String>,
    /// Maximum window size required by any operator.
    pub max_window: usize,
    /// Whether the expression contains cross-sectional operators.
    pub has_cross_sectional: bool,
    /// List of operators used in the expression.
    pub operators: Vec<String>,
    /// Estimated computational complexity.
    pub complexity: f64,
}

impl CompiledExpression {
    /// Creates a new compiled expression.
    pub fn new(node: ExprNode) -> Self {
        let mut expr = Self {
            node,
            metadata: ExpressionMetadata::default(),
        };
        expr.update_metadata();
        expr
    }
    
    /// Updates the metadata based on the expression tree.
    fn update_metadata(&mut self) {
        self.metadata = self.extract_metadata(&self.node);
    }
    
    /// Extracts metadata from an expression node.
    fn extract_metadata(&self, node: &ExprNode) -> ExpressionMetadata {
        let mut metadata = ExpressionMetadata::default();
        self.collect_metadata(node, &mut metadata);
        metadata
    }
    
    /// Recursively collects metadata from the expression tree.
    fn collect_metadata(&self, node: &ExprNode, metadata: &mut ExpressionMetadata) {
        match node {
            ExprNode::Constant(_) => {
                metadata.complexity += 0.1;
            }
            
            ExprNode::Feature(name) => {
                let feature_name = name.trim_start_matches('$');
                if !metadata.features.contains(&feature_name.to_string()) {
                    metadata.features.push(feature_name.to_string());
                }
                metadata.complexity += 0.2;
            }
            
            ExprNode::Operator { name, args, params } => {
                // Add operator to list
                if !metadata.operators.contains(name) {
                    metadata.operators.push(name.clone());
                }
                
                // Update complexity based on operator type
                metadata.complexity += match name.as_str() {
                    "Add" | "Sub" | "Mul" | "Div" => 0.3,
                    "TS_Mean" | "TS_Sum" => 1.0,
                    "TS_Std" | "TS_Var" => 2.0,
                    "TS_Skew" | "TS_Kurt" => 3.0,
                    "CS_Rank" | "CS_Zscore" => 5.0,
                    _ => 1.5,
                };
                
                // Check for cross-sectional operators
                if name.starts_with("CS_") {
                    metadata.has_cross_sectional = true;
                }
                
                // Extract window size for time-series operators
                if name.starts_with("TS_") {
                    if let Some(window) = params.get("window") {
                        metadata.max_window = metadata.max_window.max(*window as usize);
                    }
                }
                
                // Recursively process arguments
                for arg in args {
                    self.collect_metadata(&arg.node, metadata);
                }
            }
        }
    }
}

/// Result type for expression operations.
pub type ExpressionResult<T> = Result<T, ExpressionError>;

/// Errors that can occur during expression operations.
#[derive(Debug, Clone, PartialEq)]
pub enum ExpressionError {
    /// Invalid expression syntax.
    ParseError(String),
    /// Unknown operator.
    UnknownOperator(String),
    /// Invalid parameters for operator.
    InvalidParameters(String),
    /// Runtime computation error.
    ComputationError(String),
}

impl std::fmt::Display for ExpressionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::ParseError(msg) => write!(f, "Parse error: {}", msg),
            Self::UnknownOperator(op) => write!(f, "Unknown operator: {}", op),
            Self::InvalidParameters(msg) => write!(f, "Invalid parameters: {}", msg),
            Self::ComputationError(msg) => write!(f, "Computation error: {}", msg),
        }
    }
}

impl std::error::Error for ExpressionError {}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_expression_metadata() {
        // Create a simple expression: TS_Mean($close, 20)
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Feature("$close".to_string())),
                ],
                params: HashMap::from([("window".to_string(), 20.0)]),
            }
        );
        
        assert_eq!(expr.metadata.features, vec!["close"]);
        assert_eq!(expr.metadata.max_window, 20);
        assert!(!expr.metadata.has_cross_sectional);
        assert_eq!(expr.metadata.operators, vec!["TS_Mean"]);
    }
    
    #[test]
    fn test_complex_expression_metadata() {
        // Create expression: TS_Mean($close, 20) / TS_Mean($close, 50)
        let expr = CompiledExpression::new(
            ExprNode::Operator {
                name: "Div".to_string(),
                args: vec![
                    CompiledExpression::new(ExprNode::Operator {
                        name: "TS_Mean".to_string(),
                        args: vec![
                            CompiledExpression::new(ExprNode::Feature("$close".to_string())),
                        ],
                        params: HashMap::from([("window".to_string(), 20.0)]),
                    }),
                    CompiledExpression::new(ExprNode::Operator {
                        name: "TS_Mean".to_string(),
                        args: vec![
                            CompiledExpression::new(ExprNode::Feature("$close".to_string())),
                        ],
                        params: HashMap::from([("window".to_string(), 50.0)]),
                    }),
                ],
                params: HashMap::new(),
            }
        );
        
        assert_eq!(expr.metadata.features, vec!["close"]);
        assert_eq!(expr.metadata.max_window, 50);
        assert!(expr.metadata.operators.contains(&"Div".to_string()));
        assert!(expr.metadata.operators.contains(&"TS_Mean".to_string()));
    }
}