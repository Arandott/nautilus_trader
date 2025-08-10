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

"""Unit tests for FactorExp expression parser."""

import pytest

from nautilus_trader.indicators.factorexp.expressions.parser import (
    ExpressionParser,
    ParseError,
)
from nautilus_trader.indicators.factorexp.expressions.ast import (
    Feature,
    Constant,
    UnaryOp,
    BinaryOp,
    RollingOp,
    PairRollingOp,
    CrossSectionalOp,
)


class TestExpressionParser:
    """Test cases for the FactorExp expression parser."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ExpressionParser()
    
    def test_parse_feature(self):
        """Test parsing feature references."""
        # Test simple feature
        expr = self.parser.parse("$close")
        assert isinstance(expr, Feature)
        assert expr.name == "close"
        
        # Test feature with underscores
        expr = self.parser.parse("$bid_size")
        assert isinstance(expr, Feature)
        assert expr.name == "bid_size"
    
    def test_parse_constant(self):
        """Test parsing numeric constants."""
        # Integer
        expr = self.parser.parse("42")
        assert isinstance(expr, Constant)
        assert expr.value == 42.0
        
        # Float
        expr = self.parser.parse("3.14159")
        assert isinstance(expr, Constant)
        assert expr.value == 3.14159
        
        # Scientific notation
        expr = self.parser.parse("1.5e-3")
        assert isinstance(expr, Constant)
        assert expr.value == 0.0015
    
    def test_parse_binary_operations(self):
        """Test parsing binary arithmetic operations."""
        # Addition
        expr = self.parser.parse("$close + 10")
        assert isinstance(expr, BinaryOp)
        assert expr.operator == "Add"
        assert isinstance(expr.left, Feature)
        assert isinstance(expr.right, Constant)
        
        # Multiplication with parentheses
        expr = self.parser.parse("($high + $low) * 0.5")
        assert isinstance(expr, BinaryOp)
        assert expr.operator == "Mul"
        assert isinstance(expr.left, BinaryOp)
        assert expr.left.operator == "Add"
    
    def test_parse_unary_operations(self):
        """Test parsing unary operations."""
        # Log
        expr = self.parser.parse("Log($close)")
        assert isinstance(expr, UnaryOp)
        assert expr.operator == "Log"
        assert isinstance(expr.operand, Feature)
        
        # Nested unary
        expr = self.parser.parse("Abs(Sign($close))")
        assert isinstance(expr, UnaryOp)
        assert expr.operator == "Abs"
        assert isinstance(expr.operand, UnaryOp)
        assert expr.operand.operator == "Sign"
    
    def test_parse_rolling_operations(self):
        """Test parsing rolling window operations."""
        # Simple moving average
        expr = self.parser.parse("TS_Mean($close, 20)")
        assert isinstance(expr, RollingOp)
        assert expr.operator == "TS_Mean"
        assert isinstance(expr.operand, Feature)
        assert expr.window == 20
        
        # Rolling with expression
        expr = self.parser.parse("TS_Std($high - $low, 10)")
        assert isinstance(expr, RollingOp)
        assert expr.operator == "TS_Std"
        assert isinstance(expr.operand, BinaryOp)
        assert expr.window == 10
    
    def test_parse_pair_rolling_operations(self):
        """Test parsing pair rolling operations."""
        # Correlation
        expr = self.parser.parse("TS_Corr($close, $volume, 30)")
        assert isinstance(expr, PairRollingOp)
        assert expr.operator == "TS_Corr"
        assert isinstance(expr.left, Feature)
        assert isinstance(expr.right, Feature)
        assert expr.window == 30
    
    def test_parse_cross_sectional_operations(self):
        """Test parsing cross-sectional operations."""
        # Rank
        expr = self.parser.parse("CSRank($close)")
        assert isinstance(expr, CrossSectionalOp)
        assert expr.operator == "CSRank"
        assert isinstance(expr.operand, Feature)
        
        # Z-score
        expr = self.parser.parse("ZScore(TS_Mean($volume, 20))")
        assert isinstance(expr, CrossSectionalOp)
        assert expr.operator == "ZScore"
        assert isinstance(expr.operand, RollingOp)
    
    def test_parse_complex_expressions(self):
        """Test parsing complex nested expressions."""
        # Sharpe ratio approximation
        expr = self.parser.parse("TS_Mean($close, 20) / TS_Std($close, 20)")
        assert isinstance(expr, BinaryOp)
        assert expr.operator == "Div"
        assert isinstance(expr.left, RollingOp)
        assert isinstance(expr.right, RollingOp)
        
        # Multi-factor signal
        expr_str = """
        ZScore(
            0.4 * TS_Mean($close, 20) / TS_Std($close, 20) +
            0.6 * Log(TS_Mean($volume, 10))
        )
        """
        expr = self.parser.parse(expr_str)
        assert isinstance(expr, CrossSectionalOp)
        assert expr.operator == "ZScore"
    
    def test_parse_errors(self):
        """Test parsing error cases."""
        # Empty expression
        with pytest.raises(ParseError, match="Empty expression"):
            self.parser.parse("")
        
        # Invalid token
        with pytest.raises(ParseError, match="Invalid characters"):
            self.parser.parse("$close @@ 10")
        
        # Unclosed parenthesis
        with pytest.raises(ParseError, match="Expected"):
            self.parser.parse("TS_Mean($close, 20")
        
        # Wrong number of arguments
        with pytest.raises(ParseError, match="expects 2 arguments"):
            self.parser.parse("TS_Mean($close)")
        
        # Invalid window
        with pytest.raises(ParseError, match="window must be a constant"):
            self.parser.parse("TS_Mean($close, $volume)")
    
    def test_operator_precedence(self):
        """Test operator precedence in parsing."""
        # Multiplication before addition
        expr = self.parser.parse("$close + $high * 2")
        assert isinstance(expr, BinaryOp)
        assert expr.operator == "Add"
        assert isinstance(expr.right, BinaryOp)
        assert expr.right.operator == "Mul"
        
        # Power is right-associative
        expr = self.parser.parse("2 ^ 3 ^ 2")  # Should be 2^(3^2) = 2^9
        assert isinstance(expr, BinaryOp)
        assert expr.operator == "Pow"
        assert isinstance(expr.right, BinaryOp)
        assert expr.right.operator == "Pow"