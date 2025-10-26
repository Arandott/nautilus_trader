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

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

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
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CompiledExpression {
    /// The expression tree node.
    pub node: ExprNode,
    /// Metadata about the expression.
    pub metadata: ExpressionMetadata,
}

/// Metadata about an expression.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct ExpressionMetadata {
    /// List of features used in the expression.
    pub features: Vec<String>,
    /// Maximum window size required by any operator.
    pub max_window: usize,
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

        // CRITICAL FIX: Calculate true warmup depth considering nested windows
        metadata.max_window = self.calculate_warmup_depth(node);

        metadata
    }

    /// Calculates the true warmup depth considering nested window operators.
    ///
    /// For nested expressions like TS_Mean(TS_Mean($close, 5), 5):
    /// - Inner TS_Mean needs 5 bars to produce first output
    /// - Outer TS_Mean needs 5 outputs from inner (which takes 5+4=9 bars total)
    /// - Result: 9 bars, not 5!
    ///
    /// Formula: warmup = child_warmup + (window - 1)
    fn calculate_warmup_depth(&self, node: &ExprNode) -> usize {
        match node {
            // Leaf nodes need just 1 bar
            ExprNode::Constant(_) | ExprNode::Feature(_) => 1,

            ExprNode::Operator { name, args, params } => {
                // First, calculate warmup depth for all child nodes
                let child_depths: Vec<usize> = args
                    .iter()
                    .map(|arg| self.calculate_warmup_depth(&arg.node))
                    .collect();

                // Get the maximum child depth
                let max_child_depth = child_depths.iter().max().copied().unwrap_or(1);

                // Check if this operator has a window parameter
                if name.starts_with("TS_") || name == "ZScore" || name == "Demean" {
                    if let Some(window) = params.get("window") {
                        let window_size = *window as usize;
                        // CRITICAL: Windowed operators need child_depth + (window - 1)
                        // Example: TS_Mean(TS_Mean($close, 5), 5) needs 5 + (5-1) = 9 bars
                        return max_child_depth + window_size - 1;
                    }
                }

                // Non-windowed operators: just propagate max child depth
                max_child_depth
            }
        }
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
                    "And" | "Or" => 0.2,
                    "When" => 0.4,
                    "TS_Mean" | "TS_Sum" => 1.0,
                    "TS_Std" | "TS_Var" => 2.0,
                    "TS_Skew" | "TS_Kurt" => 3.0,
                    "ZScore" | "Demean" => 2.0,
                    _ => 1.5,
                };

                // Extract window size for rolling operators
                if name.starts_with("TS_") || name == "ZScore" || name == "Demean" {
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
        let expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Mean".to_string(),
            args: vec![CompiledExpression::new(ExprNode::Feature(
                "$close".to_string(),
            ))],
            params: HashMap::from([("window".to_string(), 20.0)]),
        });

        assert_eq!(expr.metadata.features, vec!["close"]);
        assert_eq!(expr.metadata.max_window, 20);
        // Cross-sectional check removed - not applicable to single instrument context
        assert_eq!(expr.metadata.operators, vec!["TS_Mean"]);
    }

    #[test]
    fn test_complex_expression_metadata() {
        // Create expression: TS_Mean($close, 20) / TS_Mean($close, 50)
        let expr = CompiledExpression::new(ExprNode::Operator {
            name: "Div".to_string(),
            args: vec![
                CompiledExpression::new(ExprNode::Operator {
                    name: "TS_Mean".to_string(),
                    args: vec![CompiledExpression::new(ExprNode::Feature(
                        "$close".to_string(),
                    ))],
                    params: HashMap::from([("window".to_string(), 20.0)]),
                }),
                CompiledExpression::new(ExprNode::Operator {
                    name: "TS_Mean".to_string(),
                    args: vec![CompiledExpression::new(ExprNode::Feature(
                        "$close".to_string(),
                    ))],
                    params: HashMap::from([("window".to_string(), 50.0)]),
                }),
            ],
            params: HashMap::new(),
        });

        assert_eq!(expr.metadata.features, vec!["close"]);
        assert_eq!(expr.metadata.max_window, 50);
        assert!(expr.metadata.operators.contains(&"Div".to_string()));
        assert!(expr.metadata.operators.contains(&"TS_Mean".to_string()));
    }

    #[test]
    fn test_nested_window_warmup() {
        // CRITICAL TEST: Verify nested window operators accumulate correctly
        // Create nested expression: TS_Mean(TS_Mean($close, 5), 5)
        let expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Mean".to_string(),
            args: vec![CompiledExpression::new(ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![CompiledExpression::new(ExprNode::Feature(
                    "$close".to_string(),
                ))],
                params: HashMap::from([("window".to_string(), 5.0)]),
            })],
            params: HashMap::from([("window".to_string(), 5.0)]),
        });

        // Should be 9, not 5:
        // - Inner TS_Mean needs 5 bars to produce first output
        // - Outer TS_Mean needs 5 outputs from inner = 5 + 4 more bars = 9 total
        assert_eq!(expr.metadata.max_window, 9);
        assert_eq!(expr.metadata.features, vec!["close"]);
        assert_eq!(expr.metadata.operators, vec!["TS_Mean"]);
    }

    #[test]
    fn test_deeply_nested_warmup() {
        // Test triple nesting: TS_Mean(TS_Mean(TS_Mean($close, 3), 3), 3)
        let expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Mean".to_string(),
            args: vec![CompiledExpression::new(ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![CompiledExpression::new(ExprNode::Operator {
                    name: "TS_Mean".to_string(),
                    args: vec![CompiledExpression::new(ExprNode::Feature(
                        "$close".to_string(),
                    ))],
                    params: HashMap::from([("window".to_string(), 3.0)]),
                })],
                params: HashMap::from([("window".to_string(), 3.0)]),
            })],
            params: HashMap::from([("window".to_string(), 3.0)]),
        });

        // Calculation:
        // - Innermost: 1 + (3-1) = 3
        // - Middle: 3 + (3-1) = 5
        // - Outer: 5 + (3-1) = 7
        assert_eq!(expr.metadata.max_window, 7);
    }

    #[test]
    fn test_asymmetric_nested_warmup() {
        // Test asymmetric nesting: TS_Mean(TS_Mean($close, 10), 5)
        let expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Mean".to_string(),
            args: vec![CompiledExpression::new(ExprNode::Operator {
                name: "TS_Mean".to_string(),
                args: vec![CompiledExpression::new(ExprNode::Feature(
                    "$close".to_string(),
                ))],
                params: HashMap::from([("window".to_string(), 10.0)]),
            })],
            params: HashMap::from([("window".to_string(), 5.0)]),
        });

        // Calculation:
        // - Inner: 1 + (10-1) = 10
        // - Outer: 10 + (5-1) = 14
        assert_eq!(expr.metadata.max_window, 14);
    }

    #[test]
    fn test_complex_real_world_expression() {
        // Test realistic expression: Clip(ZScore(TS_Std(TS_Delta($close, 1), 96), 5760), -2, 2)
        // Build from inside out: TS_Delta($close, 1)
        let delta_expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Delta".to_string(),
            args: vec![CompiledExpression::new(ExprNode::Feature(
                "$close".to_string(),
            ))],
            params: HashMap::from([("window".to_string(), 1.0)]),
        });

        // TS_Std(TS_Delta($close, 1), 96)
        let std_expr = CompiledExpression::new(ExprNode::Operator {
            name: "TS_Std".to_string(),
            args: vec![delta_expr],
            params: HashMap::from([("window".to_string(), 96.0)]),
        });

        // ZScore(TS_Std(...), 5760)
        let zscore_expr = CompiledExpression::new(ExprNode::Operator {
            name: "ZScore".to_string(),
            args: vec![std_expr],
            params: HashMap::from([("window".to_string(), 5760.0)]),
        });

        // Clip(ZScore(...), -2, 2)
        let clip_expr = CompiledExpression::new(ExprNode::Operator {
            name: "Clip".to_string(),
            args: vec![zscore_expr],
            params: HashMap::new(), // Clip doesn't have a window parameter
        });

        // Calculation:
        // - TS_Delta: 1 + (1-1) = 1
        // - TS_Std: 1 + (96-1) = 96
        // - ZScore: 96 + (5760-1) = 5855
        // - Clip: 5855 (no window, just propagates)
        assert_eq!(clip_expr.metadata.max_window, 5855);
        assert_eq!(clip_expr.metadata.features, vec!["close"]);
    }
}
