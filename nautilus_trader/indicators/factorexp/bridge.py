#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""
Bridge module for converting Python AST to Rust CompiledExpression format.

This module provides the glue between the Python expression parser and the
Rust execution engine.
"""

from typing import Dict, Any, List, Union

from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
from nautilus_trader.indicators.factorexp.expressions.ast import (
    Expression,
    Feature,
    Constant,
    UnaryOp,
    BinaryOp,
    RollingOp,
    PairRollingOp,
    CrossSectionalOp,
)


class ExpressionBridge:
    """
    Bridge for converting between Python and Rust expression representations.
    
    This class handles the conversion of Python-parsed AST to the dictionary
    format expected by the Rust compile_expression_from_python function.
    """
    
    def __init__(self):
        """Initialize the expression bridge."""
        self.parser = ExpressionParser()
    
    def parse_and_convert(self, expression_str: str) -> Dict[str, Any]:
        """
        Parse an expression string and convert to Rust-compatible format.
        
        Parameters
        ----------
        expression_str : str
            The expression string to parse (e.g., "TS_Mean($close, 20)")
            
        Returns
        -------
        Dict[str, Any]
            Dictionary representation compatible with Rust's compile_expression_from_python
        """
        # Parse the expression
        ast = self.parser.parse(expression_str)
        
        # Convert to Rust format
        return self._convert_ast_to_dict(ast)
    
    def _convert_ast_to_dict(self, expr: Expression) -> Dict[str, Any]:
        """
        Convert a Python AST node to dictionary format.
        
        Parameters
        ----------
        expr : Expression
            The AST node to convert
            
        Returns
        -------
        Dict[str, Any]
            Dictionary representation of the node
        """
        if isinstance(expr, Feature):
            return {
                "type": "Feature",
                "name": f"${expr.name}"  # Ensure $ prefix
            }
        
        elif isinstance(expr, Constant):
            return {
                "type": "Constant",
                "value": float(expr.value)
            }
        
        elif isinstance(expr, UnaryOp):
            return {
                "type": "Operator",
                "name": expr.operator,
                "args": [self._convert_ast_to_dict(expr.operand)],
                "params": {}
            }
        
        elif isinstance(expr, BinaryOp):
            # Map Python operator names to Rust operator names
            operator_map = {
                '+': 'Add',
                '-': 'Sub',
                '*': 'Mul',
                '/': 'Div',
                '^': 'Pow',
                '>': 'Greater',
                '<': 'Less',
                '>=': 'GreaterEq',
                '<=': 'LessEq',
                '==': 'Equal',
                '!=': 'NotEqual',
            }
            
            operator_name = operator_map.get(expr.operator, expr.operator)
            
            return {
                "type": "Operator",
                "name": operator_name,
                "args": [
                    self._convert_ast_to_dict(expr.left),
                    self._convert_ast_to_dict(expr.right)
                ],
                "params": {}
            }
        
        elif isinstance(expr, RollingOp):
            return {
                "type": "Operator",
                "name": expr.operator,
                "args": [self._convert_ast_to_dict(expr.operand)],
                "params": {
                    "window": float(expr.window)
                }
            }
        
        elif isinstance(expr, PairRollingOp):
            return {
                "type": "Operator",
                "name": expr.operator,
                "args": [
                    self._convert_ast_to_dict(expr.left),
                    self._convert_ast_to_dict(expr.right)
                ],
                "params": {
                    "window": float(expr.window)
                }
            }
        
        elif isinstance(expr, CrossSectionalOp):
            params = {}
            if hasattr(expr, 'quantile'):
                params["quantile"] = float(expr.quantile)
            
            return {
                "type": "Operator",
                "name": expr.operator,
                "args": [self._convert_ast_to_dict(expr.operand)],
                "params": params
            }
        
        else:
            raise ValueError(f"Unknown expression type: {type(expr)}")


# Global instance for convenience
_bridge = ExpressionBridge()


def parse_expression(expression_str: str) -> Dict[str, Any]:
    """
    Parse an expression string and convert to Rust format.
    
    This is a convenience function that uses the global bridge instance.
    
    Parameters
    ----------
    expression_str : str
        The expression string to parse
        
    Returns
    -------
    Dict[str, Any]
        Dictionary representation for Rust
        
    Examples
    --------
    >>> ast_dict = parse_expression("TS_Mean($close, 20)")
    >>> ast_dict = parse_expression("TS_Mean($close, 20) / TS_Mean($close, 50)")
    """
    return _bridge.parse_and_convert(expression_str)


def compile_expression(expression_str: str):
    """
    Compile an expression string to Rust CompiledExpression.
    
    This function parses the expression and calls the Rust
    compile_expression_from_python function.
    
    Parameters
    ----------
    expression_str : str
        The expression string to compile
        
    Returns
    -------
    CompiledExpression
        The compiled expression ready for execution
    """
    try:
        from nautilus_trader.core.nautilus_pyo3.factorexp import compile_expression_from_python
    except ImportError as e:
        raise ImportError(
            "Rust factorexp module not available. "
            "Please ensure the crate is compiled with 'make build'."
        ) from e
    
    # Parse and convert to dictionary
    ast_dict = parse_expression(expression_str)
    
    # Call Rust function to compile
    return compile_expression_from_python(ast_dict)


if __name__ == "__main__":
    # Test the bridge
    bridge = ExpressionBridge()
    
    # Test simple expression
    expr = "$close"
    result = bridge.parse_and_convert(expr)
    print(f"Simple feature: {result}")
    
    # Test rolling operator
    expr = "TS_Mean($close, 20)"
    result = bridge.parse_and_convert(expr)
    print(f"Rolling mean: {result}")
    
    # Test complex expression
    expr = "TS_Mean($close, 20) / TS_Mean($close, 50)"
    result = bridge.parse_and_convert(expr)
    print(f"MA ratio: {result}")
    
    # Test with cross-sectional
    expr = "CSRank(TS_Mean($close, 20))"
    result = bridge.parse_and_convert(expr)
    print(f"Cross-sectional rank: {result}")