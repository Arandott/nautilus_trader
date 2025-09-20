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

//! Simple, direct expression parser for FactorExp.
//!
//! Following Linus's philosophy: "Perfection is achieved not when there is
//! nothing more to add, but when there is nothing left to take away."

use std::collections::HashMap;
use crate::expression::{CompiledExpression, ExprNode};

/// Expression tree node - clear semantic naming following the xxxNode convention.
/// NO trait objects, NO virtual dispatch, pure enum-based.
#[derive(Debug, Clone, PartialEq)]
pub enum Expr {
    /// Constant number node
    NumNode(f64),

    /// Variable reference node (e.g., $close, $volume)
    VarNode(String),

    /// Binary operation node
    BinOpNode {
        /// Binary operation type
        op: BinOpType,
        /// Left operand node
        left: Box<Expr>,
        /// Right operand node
        right: Box<Expr>,
    },

    /// Unary operation node
    UnOpNode {
        /// Unary operation type
        op: UnOpType,
        /// Argument node
        arg: Box<Expr>,
    },

    /// Rolling window operation node
    RollingNode {
        /// Rolling operation type
        op: RollingOpType,
        /// Argument node
        arg: Box<Expr>,
        /// Window size
        window: usize,
        /// Additional parameters (e.g., phi for quantile)
        params: HashMap<String, f64>,
    },

    /// Pair rolling operation node (correlation, covariance, etc.)
    PairRollingNode {
        /// Pair rolling operation type
        op: PairRollingOpType,
        /// Left argument node
        left: Box<Expr>,
        /// Right argument node
        right: Box<Expr>,
        /// Window size
        window: usize,
    },

    /// Ternary operation node (When/If-Then-Else)
    TernaryNode {
        /// Condition expression
        condition: Box<Expr>,
        /// Value if condition is true
        true_value: Box<Expr>,
        /// Value if condition is false
        false_value: Box<Expr>,
    },

    /// Clip operation node (bounds value within min/max range)
    ClipNode {
        /// Value expression to clip
        value: Box<Expr>,
        /// Minimum bound
        min: Box<Expr>,
        /// Maximum bound
        max: Box<Expr>,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinOpType {
    Add, Sub, Mul, Div, Pow,
    Greater, Less, GreaterEq, LessEq, Equal, NotEqual,
    And, Or, Max, Min,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnOpType {
    Neg, Abs, Sign, Sqrt, Exp,
    Log, Log10, Sin, Cos, Tan,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RollingOpType {
    Mean, Sum, Std, Var, Min, Max, Median,
    Skew, Kurt, Mad, EMA, WMA,
    Delta, Ref, Rank, Argmax, Argmin, Product,
    ZScore, Demean, Quantile,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PairRollingOpType {
    Corr, Cov, Beta,
}

/// Simple recursive descent parser - no external dependencies, no complexity.
pub struct Parser {
    input: Vec<char>,
    pos: usize,
}

impl Parser {
    /// Create a new parser for the given expression.
    pub fn new(expr: &str) -> Self {
        Self {
            input: expr.chars().collect(),
            pos: 0,
        }
    }

    /// Parse the expression.
    pub fn parse(&mut self) -> Result<Expr, String> {
        self.skip_whitespace();
        let result = self.parse_expr()?;
        self.skip_whitespace();

        if self.pos < self.input.len() {
            return Err(format!("Unexpected character at position {}", self.pos));
        }

        Ok(result)
    }

    fn parse_expr(&mut self) -> Result<Expr, String> {
        self.parse_additive()
    }

    fn parse_additive(&mut self) -> Result<Expr, String> {
        let mut left = self.parse_multiplicative()?;

        loop {
            self.skip_whitespace();

            let op = if self.consume_char('+') {
                BinOpType::Add
            } else if self.consume_char('-') {
                BinOpType::Sub
            } else {
                break;
            };

            let right = self.parse_multiplicative()?;
            left = Expr::BinOpNode {
                op,
                left: Box::new(left),
                right: Box::new(right),
            };
        }

        Ok(left)
    }

    fn parse_multiplicative(&mut self) -> Result<Expr, String> {
        let mut left = self.parse_power()?;

        loop {
            self.skip_whitespace();

            let op = if self.consume_char('*') {
                BinOpType::Mul
            } else if self.consume_char('/') {
                BinOpType::Div
            } else {
                break;
            };

            let right = self.parse_power()?;
            left = Expr::BinOpNode {
                op,
                left: Box::new(left),
                right: Box::new(right),
            };
        }

        Ok(left)
    }

    fn parse_power(&mut self) -> Result<Expr, String> {
        let mut left = self.parse_unary()?;

        self.skip_whitespace();
        if self.consume_char('^') {
            let right = self.parse_power()?; // Right associative
            left = Expr::BinOpNode {
                op: BinOpType::Pow,
                left: Box::new(left),
                right: Box::new(right),
            };
        }

        Ok(left)
    }

    fn parse_unary(&mut self) -> Result<Expr, String> {
        self.skip_whitespace();

        if self.consume_char('-') {
            let arg = self.parse_unary()?;
            return Ok(Expr::UnOpNode {
                op: UnOpType::Neg,
                arg: Box::new(arg),
            });
        }

        self.parse_atom()
    }

    fn parse_atom(&mut self) -> Result<Expr, String> {
        self.skip_whitespace();

        // Parenthesized expression
        if self.consume_char('(') {
            let expr = self.parse_expr()?;
            self.skip_whitespace();
            if !self.consume_char(')') {
                return Err(format!("Expected ')' at position {}", self.pos));
            }
            return Ok(expr);
        }

        // Variable
        if self.peek_char() == Some('$') {
            return self.parse_variable();
        }

        // Function call
        if self.peek_char().map_or(false, |c| c.is_ascii_alphabetic()) {
            return self.parse_function();
        }

        // Number
        if self.peek_char().map_or(false, |c| c.is_ascii_digit() || c == '.') {
            return self.parse_number();
        }

        Err(format!("Unexpected token at position {}", self.pos))
    }

    fn parse_variable(&mut self) -> Result<Expr, String> {
        self.consume_char('$');
        let name = self.parse_identifier()?;
        Ok(Expr::VarNode(name))
    }

    fn parse_function(&mut self) -> Result<Expr, String> {
        let name = self.parse_identifier()?;

        self.skip_whitespace();
        if !self.consume_char('(') {
            return Err(format!("Expected '(' after function name at position {}", self.pos));
        }

        let args = self.parse_args()?;

        self.skip_whitespace();
        if !self.consume_char(')') {
            return Err(format!("Expected ')' at position {}", self.pos));
        }

        // Match function name to operation type
        self.build_function_expr(&name, args)
    }

    fn parse_args(&mut self) -> Result<Vec<Expr>, String> {
        let mut args = Vec::new();

        self.skip_whitespace();
        if self.peek_char() == Some(')') {
            return Ok(args);
        }

        loop {
            args.push(self.parse_expr()?);
            self.skip_whitespace();

            if !self.consume_char(',') {
                break;
            }
        }

        Ok(args)
    }

    fn parse_number(&mut self) -> Result<Expr, String> {
        let start = self.pos;
        let mut has_e = false;
        let mut after_e = false;

        while let Some(c) = self.peek_char() {
            match c {
                '0'..='9' | '.' => {
                    self.advance();
                    after_e = false;
                }
                'e' | 'E' if !has_e => {
                    self.advance();
                    has_e = true;
                    after_e = true;
                }
                '+' | '-' if after_e => {
                    // Only accept +/- immediately after e/E for scientific notation
                    self.advance();
                    after_e = false;
                }
                _ => break,
            }
        }

        let num_str: String = self.input[start..self.pos].iter().collect();
        num_str.parse::<f64>()
            .map(Expr::NumNode)
            .map_err(|_| format!("Invalid number: {}", num_str))
    }

    fn parse_identifier(&mut self) -> Result<String, String> {
        let start = self.pos;

        while let Some(c) = self.peek_char() {
            if c.is_ascii_alphanumeric() || c == '_' {
                self.advance();
            } else {
                break;
            }
        }

        if self.pos == start {
            return Err(format!("Expected identifier at position {}", self.pos));
        }

        Ok(self.input[start..self.pos].iter().collect())
    }

    fn build_function_expr(&self, name: &str, args: Vec<Expr>) -> Result<Expr, String> {
        // Special handling for ZScore and Demean - they can be called without TS_ prefix
        if name == "ZScore" || name == "Demean" {
            return self.build_rolling_expr(name, args);
        }

        // Match rolling operators
        if name.starts_with("TS_") {
            let op_name = &name[3..];
            return self.build_rolling_expr(op_name, args);
        }

        // Match unary operators
        if let Ok(op) = self.parse_unary_op(name) {
            if args.len() != 1 {
                return Err(format!("{} expects 1 argument, got {}", name, args.len()));
            }
            return Ok(Expr::UnOpNode {
                op,
                arg: Box::new(args.into_iter().next().ok_or("Missing argument")?),
            });
        }

        // Special handling for When - it's a ternary operator
        if name == "When" {
            if args.len() != 3 {
                return Err(format!("When expects 3 arguments (condition, true_value, false_value), got {}", args.len()));
            }
            let mut iter = args.into_iter();
            return Ok(Expr::TernaryNode {
                condition: Box::new(iter.next().ok_or("Missing condition")?),
                true_value: Box::new(iter.next().ok_or("Missing true value")?),
                false_value: Box::new(iter.next().ok_or("Missing false value")?),
            });
        }

        // Special handling for Clip - bounds value within min/max range
        if name == "Clip" {
            if args.len() != 3 {
                return Err(format!("Clip expects 3 arguments (value, min, max), got {}", args.len()));
            }
            let mut iter = args.into_iter();
            return Ok(Expr::ClipNode {
                value: Box::new(iter.next().ok_or("Missing value")?),
                min: Box::new(iter.next().ok_or("Missing min")?),
                max: Box::new(iter.next().ok_or("Missing max")?),
            });
        }

        // Match binary operators
        if let Ok(op) = self.parse_binary_op(name) {
            if args.len() != 2 {
                return Err(format!("{} expects 2 arguments, got {}", name, args.len()));
            }
            let mut iter = args.into_iter();
            return Ok(Expr::BinOpNode {
                op,
                left: Box::new(iter.next().ok_or("Missing first argument")?),
                right: Box::new(iter.next().ok_or("Missing second argument")?),
            });
        }

        Err(format!("Unknown function: {}", name))
    }

    fn build_rolling_expr(&self, op_name: &str, args: Vec<Expr>) -> Result<Expr, String> {
        // Check if it's a pair rolling operator
        if let Ok(op) = self.parse_pair_rolling_op(op_name) {
            if args.len() != 3 {
                return Err(format!("TS_{} expects 3 arguments, got {}", op_name, args.len()));
            }

            let mut iter = args.into_iter();
            let left = iter.next().ok_or("Missing first argument")?;
            let right = iter.next().ok_or("Missing second argument")?;
            let window_expr = iter.next().ok_or("Missing window argument")?;

            let window = match window_expr {
                Expr::NumNode(n) if n > 0.0 => n as usize,
                _ => return Err(format!("Window must be a positive number")),
            };

            return Ok(Expr::PairRollingNode {
                op,
                left: Box::new(left),
                right: Box::new(right),
                window,
            });
        }

        // Single rolling operator
        if let Ok(op) = self.parse_rolling_op(op_name) {
            // Special handling for Quantile - expects 3 arguments (expr, window, phi)
            if op == RollingOpType::Quantile {
                if args.len() != 3 {
                    return Err(format!("TS_Quantile expects 3 arguments (expr, window, phi), got {}", args.len()));
                }

                let mut iter = args.into_iter();
                let arg = iter.next().ok_or("Missing expression argument")?;
                let window_expr = iter.next().ok_or("Missing window argument")?;
                let phi_expr = iter.next().ok_or("Missing phi argument")?;

                let window = match window_expr {
                    Expr::NumNode(n) if n > 0.0 => n as usize,
                    _ => return Err("Window must be a positive number".to_string()),
                };

                let phi = match phi_expr {
                    Expr::NumNode(p) if p >= 0.0 && p <= 1.0 => p,
                    _ => return Err("Quantile phi must be a number between 0 and 1".to_string()),
                };

                let mut params = HashMap::new();
                params.insert("phi".to_string(), phi);

                return Ok(Expr::RollingNode {
                    op,
                    arg: Box::new(arg),
                    window,
                    params,
                });
            }

            // Standard rolling operators - 2 arguments
            if args.len() != 2 {
                return Err(format!("TS_{} expects 2 arguments, got {}", op_name, args.len()));
            }

            let mut iter = args.into_iter();
            let arg = iter.next().ok_or("Missing argument")?;
            let window_expr = iter.next().ok_or("Missing window argument")?;

            let window = match window_expr {
                Expr::NumNode(n) if n > 0.0 => n as usize,
                _ => return Err(format!("Window must be a positive number")),
            };

            return Ok(Expr::RollingNode {
                op,
                arg: Box::new(arg),
                window,
                params: HashMap::new(),
            });
        }

        Err(format!("Unknown rolling operator: TS_{}", op_name))
    }

    fn parse_unary_op(&self, name: &str) -> Result<UnOpType, String> {
        match name {
            "Neg" => Ok(UnOpType::Neg),
            "Abs" => Ok(UnOpType::Abs),
            "Sign" => Ok(UnOpType::Sign),
            "Sqrt" => Ok(UnOpType::Sqrt),
            "Exp" => Ok(UnOpType::Exp),
            "Log" => Ok(UnOpType::Log),
            "Log10" => Ok(UnOpType::Log10),
            "Sin" => Ok(UnOpType::Sin),
            "Cos" => Ok(UnOpType::Cos),
            "Tan" => Ok(UnOpType::Tan),
            _ => Err(format!("Unknown unary operator: {}", name)),
        }
    }

    fn parse_binary_op(&self, name: &str) -> Result<BinOpType, String> {
        match name {
            "Add" => Ok(BinOpType::Add),
            "Sub" => Ok(BinOpType::Sub),
            "Mul" => Ok(BinOpType::Mul),
            "Div" => Ok(BinOpType::Div),
            "Pow" => Ok(BinOpType::Pow),
            "Greater" => Ok(BinOpType::Greater),
            "Less" => Ok(BinOpType::Less),
            "GreaterEq" => Ok(BinOpType::GreaterEq),
            "LessEq" => Ok(BinOpType::LessEq),
            "Equal" => Ok(BinOpType::Equal),
            "NotEqual" => Ok(BinOpType::NotEqual),
            "And" => Ok(BinOpType::And),
            "Or" => Ok(BinOpType::Or),
            "Max" => Ok(BinOpType::Max),
            "Min" => Ok(BinOpType::Min),
            _ => Err(format!("Unknown binary operator: {}", name)),
        }
    }

    fn parse_rolling_op(&self, name: &str) -> Result<RollingOpType, String> {
        match name {
            "Mean" => Ok(RollingOpType::Mean),
            "Sum" => Ok(RollingOpType::Sum),
            "Std" => Ok(RollingOpType::Std),
            "Var" => Ok(RollingOpType::Var),
            "Min" => Ok(RollingOpType::Min),
            "Max" => Ok(RollingOpType::Max),
            "Med" | "Median" => Ok(RollingOpType::Median),
            "Skew" => Ok(RollingOpType::Skew),
            "Kurt" | "Kurtosis" => Ok(RollingOpType::Kurt),
            "Mad" => Ok(RollingOpType::Mad),
            "EMA" => Ok(RollingOpType::EMA),
            "WMA" => Ok(RollingOpType::WMA),
            "Delta" => Ok(RollingOpType::Delta),
            "Ref" => Ok(RollingOpType::Ref),
            "Rank" => Ok(RollingOpType::Rank),
            "Argmax" => Ok(RollingOpType::Argmax),
            "Argmin" => Ok(RollingOpType::Argmin),
            "Product" => Ok(RollingOpType::Product),
            "ZScore" => Ok(RollingOpType::ZScore),
            "Demean" => Ok(RollingOpType::Demean),
            "Quantile" => Ok(RollingOpType::Quantile),
            _ => Err(format!("Unknown rolling operator: {}", name)),
        }
    }

    fn parse_pair_rolling_op(&self, name: &str) -> Result<PairRollingOpType, String> {
        match name {
            "Corr" => Ok(PairRollingOpType::Corr),
            "Cov" => Ok(PairRollingOpType::Cov),
            "Beta" => Ok(PairRollingOpType::Beta),
            _ => Err(format!("Unknown pair rolling operator: {}", name)),
        }
    }

    // Helper methods
    fn skip_whitespace(&mut self) {
        while let Some(c) = self.peek_char() {
            if c.is_whitespace() {
                self.advance();
            } else {
                break;
            }
        }
    }

    fn peek_char(&self) -> Option<char> {
        self.input.get(self.pos).copied()
    }

    fn advance(&mut self) {
        self.pos += 1;
    }

    fn consume_char(&mut self, expected: char) -> bool {
        if self.peek_char() == Some(expected) {
            self.advance();
            true
        } else {
            false
        }
    }
}

/// Convert parser's Expr (with XXXNode variants) to expression's ExprNode format.
/// This bridges the gap between the readable parser AST and the execution engine format.
pub fn convert_to_expr_node(expr: Expr) -> ExprNode {
    match expr {
        Expr::NumNode(value) => ExprNode::Constant(value),
        Expr::VarNode(name) => ExprNode::Feature(format!("${}", name.trim_start_matches('$'))),

        Expr::BinOpNode { op, left, right } => {
            let op_name = match op {
                BinOpType::Add => "Add",
                BinOpType::Sub => "Sub",
                BinOpType::Mul => "Mul",
                BinOpType::Div => "Div",
                BinOpType::Pow => "Pow",
                BinOpType::Greater => "Greater",
                BinOpType::Less => "Less",
                BinOpType::GreaterEq => "GreaterEq",
                BinOpType::LessEq => "LessEq",
                BinOpType::Equal => "Equal",
                BinOpType::NotEqual => "NotEqual",
                BinOpType::And => "And",
                BinOpType::Or => "Or",
                BinOpType::Max => "Max",
                BinOpType::Min => "Min",
            };

            ExprNode::Operator {
                name: op_name.to_string(),
                args: vec![
                    CompiledExpression::new(convert_to_expr_node(*left)),
                    CompiledExpression::new(convert_to_expr_node(*right)),
                ],
                params: HashMap::new(),
            }
        }

        Expr::UnOpNode { op, arg } => {
            let op_name = match op {
                UnOpType::Neg => "Neg",
                UnOpType::Abs => "Abs",
                UnOpType::Sign => "Sign",
                UnOpType::Sqrt => "Sqrt",
                UnOpType::Exp => "Exp",
                UnOpType::Log => "Log",
                UnOpType::Log10 => "Log10",
                UnOpType::Sin => "Sin",
                UnOpType::Cos => "Cos",
                UnOpType::Tan => "Tan",
            };

            ExprNode::Operator {
                name: op_name.to_string(),
                args: vec![CompiledExpression::new(convert_to_expr_node(*arg))],
                params: HashMap::new(),
            }
        }

        Expr::RollingNode { op, arg, window, params: extra_params } => {
            let op_name = match op {
                RollingOpType::Mean => "TS_Mean",
                RollingOpType::Sum => "TS_Sum",
                RollingOpType::Std => "TS_Std",
                RollingOpType::Var => "TS_Var",
                RollingOpType::Min => "TS_Min",
                RollingOpType::Max => "TS_Max",
                RollingOpType::Median => "TS_Median",
                RollingOpType::Skew => "TS_Skew",
                RollingOpType::Kurt => "TS_Kurt",
                RollingOpType::Mad => "TS_Mad",
                RollingOpType::EMA => "TS_EMA",
                RollingOpType::WMA => "TS_WMA",
                RollingOpType::Delta => "TS_Delta",
                RollingOpType::Ref => "TS_Ref",
                RollingOpType::Rank => "TS_Rank",
                RollingOpType::Argmax => "TS_Argmax",
                RollingOpType::Argmin => "TS_Argmin",
                RollingOpType::Product => "TS_Product",
                RollingOpType::ZScore => "ZScore",
                RollingOpType::Demean => "Demean",
                RollingOpType::Quantile => "TS_Quantile",
            };

            let mut params = HashMap::new();
            params.insert("window".to_string(), window as f64);

            // Add any extra parameters (e.g., phi for quantile)
            for (key, value) in extra_params {
                params.insert(key, value);
            }

            ExprNode::Operator {
                name: op_name.to_string(),
                args: vec![CompiledExpression::new(convert_to_expr_node(*arg))],
                params,
            }
        }

        Expr::PairRollingNode { op, left, right, window } => {
            let op_name = match op {
                PairRollingOpType::Corr => "TS_Corr",
                PairRollingOpType::Cov => "TS_Cov",
                PairRollingOpType::Beta => "TS_Beta",
            };

            let mut params = HashMap::new();
            params.insert("window".to_string(), window as f64);

            ExprNode::Operator {
                name: op_name.to_string(),
                args: vec![
                    CompiledExpression::new(convert_to_expr_node(*left)),
                    CompiledExpression::new(convert_to_expr_node(*right)),
                ],
                params,
            }
        }
        Expr::TernaryNode { condition, true_value, false_value } => {
            // When operator needs 3 arguments: condition, true_value, false_value
            ExprNode::Operator {
                name: "When".to_string(),
                args: vec![
                    CompiledExpression::new(convert_to_expr_node(*condition)),
                    CompiledExpression::new(convert_to_expr_node(*true_value)),
                    CompiledExpression::new(convert_to_expr_node(*false_value)),
                ],
                params: HashMap::new(),
            }
        }
        Expr::ClipNode { value, min, max } => {
            // Clip operator needs 3 arguments: value, min, max
            ExprNode::Operator {
                name: "Clip".to_string(),
                args: vec![
                    CompiledExpression::new(convert_to_expr_node(*value)),
                    CompiledExpression::new(convert_to_expr_node(*min)),
                    CompiledExpression::new(convert_to_expr_node(*max)),
                ],
                params: HashMap::new(),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_variable() {
        let mut parser = Parser::new("$close");
        let expr = parser.parse().unwrap();

        assert!(matches!(expr, Expr::VarNode(name) if name == "close"));
    }

    #[test]
    fn test_parse_number() {
        let mut parser = Parser::new("42.5");
        let expr = parser.parse().unwrap();

        assert!(matches!(expr, Expr::NumNode(n) if (n - 42.5).abs() < f64::EPSILON));
    }

    #[test]
    fn test_parse_simple_addition() {
        let mut parser = Parser::new("$close + 10");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::BinOpNode { op: BinOpType::Add, left, right } => {
                if let Expr::VarNode(name) = left.as_ref() {
                    assert_eq!(name, "close");
                } else {
                    panic!("Expected Var");
                }
                assert!(matches!(right.as_ref(), Expr::NumNode(n) if *n == 10.0));
            }
            _ => panic!("Expected Add operation"),
        }
    }

    #[test]
    fn test_parse_rolling_mean() {
        let mut parser = Parser::new("TS_Mean($close, 20)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::RollingNode { op: RollingOpType::Mean, arg, window: 20, params: _ } => {
                if let Expr::VarNode(name) = arg.as_ref() {
                    assert_eq!(name, "close");
                } else {
                    panic!("Expected Var");
                }
            }
            _ => panic!("Expected TS_Mean operation"),
        }
    }

    #[test]
    fn test_parse_complex_expression() {
        let mut parser = Parser::new("TS_Mean($close, 20) / TS_Std($close, 20)");
        let expr = parser.parse().unwrap();

        assert!(matches!(expr, Expr::BinOpNode { op: BinOpType::Div, .. }));
    }

    #[test]
    fn test_parse_ts_quantile() {
        let mut parser = Parser::new("TS_Quantile($close, 100, 0.75)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::RollingNode { op: RollingOpType::Quantile, arg, window: 100, params } => {
                if let Expr::VarNode(name) = arg.as_ref() {
                    assert_eq!(name, "close");
                } else {
                    panic!("Expected Var");
                }
                // Check that phi parameter was stored correctly
                assert_eq!(params.get("phi"), Some(&0.75));
            }
            _ => panic!("Expected TS_Quantile operation"),
        }
    }

    #[test]
    fn test_parse_pair_rolling() {
        let mut parser = Parser::new("TS_Corr($close, $volume, 30)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::PairRollingNode { op: PairRollingOpType::Corr, left, right, window: 30 } => {
                if let Expr::VarNode(name) = left.as_ref() {
                    assert_eq!(name, "close");
                } else {
                    panic!("Expected left Var");
                }
                if let Expr::VarNode(name) = right.as_ref() {
                    assert_eq!(name, "volume");
                } else {
                    panic!("Expected right Var");
                }
            }
            _ => panic!("Expected TS_Corr operation"),
        }
    }

    #[test]
    fn test_parse_nested_expression() {
        let mut parser = Parser::new("($close + $open) / 2");
        let expr = parser.parse().unwrap();

        assert!(matches!(expr, Expr::BinOpNode { op: BinOpType::Div, .. }));
    }

    #[test]
    fn test_parse_unary_operator() {
        let mut parser = Parser::new("Abs($close - 100)");
        let expr = parser.parse().unwrap();

        assert!(matches!(expr, Expr::UnOpNode { op: UnOpType::Abs, .. }));
    }

    #[test]
    fn test_parse_invalid_expression() {
        let mut parser = Parser::new("invalid expression");
        let result = parser.parse();

        assert!(result.is_err());
    }

    #[test]
    fn test_parse_empty_expression() {
        let mut parser = Parser::new("");
        let result = parser.parse();

        assert!(result.is_err());
    }

    #[test]
    fn test_parse_when_operator() {
        let mut parser = Parser::new("When($close > 100, $high, $low)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::TernaryNode { condition, true_value, false_value } => {
                // Check condition is a Greater comparison
                assert!(matches!(condition.as_ref(), Expr::BinOpNode { op: BinOpType::Greater, .. }));
                // Check true_value is $high
                assert!(matches!(true_value.as_ref(), Expr::VarNode(name) if name == "high"));
                // Check false_value is $low
                assert!(matches!(false_value.as_ref(), Expr::VarNode(name) if name == "low"));
            }
            _ => panic!("Expected TernaryNode for When operator"),
        }
    }

    #[test]
    fn test_parse_clip_operator() {
        let mut parser = Parser::new("Clip($close, 0, 100)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::ClipNode { value, min, max } => {
                // Check value is $close
                assert!(matches!(value.as_ref(), Expr::VarNode(name) if name == "close"));
                // Check min is 0
                assert!(matches!(min.as_ref(), Expr::NumNode(val) if *val == 0.0));
                // Check max is 100
                assert!(matches!(max.as_ref(), Expr::NumNode(val) if *val == 100.0));
            }
            _ => panic!("Expected ClipNode for Clip operator"),
        }
    }

    #[test]
    fn test_parse_clip_with_expressions() {
        let mut parser = Parser::new("Clip($close * 2, $low, $high)");
        let expr = parser.parse().unwrap();

        match expr {
            Expr::ClipNode { value, min, max } => {
                // Check value is multiplication
                assert!(matches!(value.as_ref(), Expr::BinOpNode { op: BinOpType::Mul, .. }));
                // Check min is $low
                assert!(matches!(min.as_ref(), Expr::VarNode(name) if name == "low"));
                // Check max is $high
                assert!(matches!(max.as_ref(), Expr::VarNode(name) if name == "high"));
            }
            _ => panic!("Expected ClipNode for Clip operator"),
        }
    }
}