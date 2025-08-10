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

"""Unit tests for FactorExp expression validator."""

import pytest

from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
from nautilus_trader.indicators.factorexp.expressions.validator import (
    ExpressionValidator,
    ValidationResult,
)
from nautilus_trader.indicators.factorexp.expressions.ast import (
    Feature,
    Constant,
    BinaryOp,
    UnaryOp,
    RollingOp,
)


class TestExpressionValidator:
    """Test cases for the FactorExp expression validator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ExpressionParser()
        self.validator = ExpressionValidator()
    
    def test_validate_simple_expression(self):
        """Test validation of simple valid expressions."""
        # Simple feature
        expr = self.parser.parse("$close")
        result = self.validator.validate(expr)
        assert result.is_valid
        assert result.error is None
        
        # Simple arithmetic
        expr = self.parser.parse("$high + $low")
        result = self.validator.validate(expr)
        assert result.is_valid
        
        # Rolling operation
        expr = self.parser.parse("TS_Mean($close, 20)")
        result = self.validator.validate(expr)
        assert result.is_valid
    
    def test_validate_depth_limit(self):
        """Test expression depth validation."""
        # Create deeply nested expression
        deep_expr = "$close"
        for i in range(15):
            deep_expr = f"Log({deep_expr})"
        
        expr = self.parser.parse(deep_expr)
        result = self.validator.validate(expr)
        assert not result.is_valid
        assert "depth" in result.error.lower()
    
    def test_validate_window_limits(self):
        """Test window size validation."""
        # Valid window
        expr = self.parser.parse("TS_Mean($close, 100)")
        result = self.validator.validate(expr)
        assert result.is_valid
        
        # Too large window
        validator = ExpressionValidator(max_window=100)
        expr = self.parser.parse("TS_Mean($close, 200)")
        result = validator.validate(expr)
        assert not result.is_valid
        assert "window size" in result.error.lower()
    
    def test_validate_feature_names(self):
        """Test feature name validation."""
        # Valid feature names
        valid_features = ["close", "open", "high", "low", "volume", "bid_size"]
        for feature in valid_features:
            expr = self.parser.parse(f"${feature}")
            result = self.validator.validate(expr)
            assert result.is_valid
        
        # Dangerous patterns
        validator = ExpressionValidator()
        dangerous_exprs = [
            Feature("__class__"),
            Feature("eval"),
            Feature("../../etc/passwd"),
        ]
        
        for expr in dangerous_exprs:
            result = validator.validate(expr)
            assert not result.is_valid
            assert "forbidden" in result.error.lower()
    
    def test_validate_operator_whitelist(self):
        """Test operator whitelisting."""
        # Create validator with limited operators
        validator = ExpressionValidator(
            allowed_operators={"Add", "Sub", "TS_Mean"}
        )
        
        # Allowed operator
        expr = self.parser.parse("TS_Mean($close, 20)")
        result = validator.validate(expr)
        assert result.is_valid
        
        # Forbidden operator
        expr = self.parser.parse("Log($close)")
        result = validator.validate(expr)
        assert not result.is_valid
        assert "forbidden operator" in result.error.lower()
    
    def test_validate_constant_limits(self):
        """Test constant value validation."""
        # Valid constant
        expr = self.parser.parse("$close * 2.5")
        result = self.validator.validate(expr)
        assert result.is_valid
        
        # Extreme constant
        validator = ExpressionValidator(max_constant=1000)
        expr = self.parser.parse("$close * 10000")
        result = validator.validate(expr)
        assert not result.is_valid
        assert "constant value" in result.error.lower()
    
    def test_validate_warnings(self):
        """Test validation warnings."""
        # Large window warning
        expr = self.parser.parse("TS_Mean($close, 1500)")
        result = self.validator.validate(expr)
        assert result.is_valid
        assert len(result.warnings) > 0
        assert "large window" in result.warnings[0].lower()
        
        # Non-standard feature warning
        expr = self.parser.parse("$custom_feature")
        result = self.validator.validate(expr)
        assert result.is_valid
        assert len(result.warnings) > 0
        assert "non-standard" in result.warnings[0].lower()
    
    def test_validate_mathematical_constraints(self):
        """Test mathematical constraint validation."""
        # Division by zero
        expr = self.parser.parse("$close / 0")
        result = self.validator.validate(expr)
        assert not result.is_valid
        assert "division by zero" in result.error.lower()
        
        # Log of negative constant
        expr = Constant(-5)
        log_expr = UnaryOp("Log", expr)
        result = self.validator.validate(log_expr)
        assert not result.is_valid
        assert "non-positive" in result.error.lower()
    
    def test_validate_cross_sectional_operations(self):
        """Test cross-sectional operation validation."""
        # Valid cross-sectional
        expr = self.parser.parse("CSRank($close)")
        result = self.validator.validate(expr)
        assert result.is_valid
        assert result.has_warnings
        assert "cross-sectional" in result.warnings[0].lower()
        
        # Check metadata
        assert result.metadata['has_cross_sectional'] is True
    
    def test_validate_metadata(self):
        """Test validation metadata generation."""
        expr = self.parser.parse("""
            TS_Mean($close, 20) / TS_Std($close, 20) + 
            CSRank($volume)
        """)
        result = self.validator.validate(expr)
        
        assert result.is_valid
        assert 'depth' in result.metadata
        assert 'operator_count' in result.metadata
        assert 'feature_count' in result.metadata
        assert 'unique_features' in result.metadata
        assert 'estimated_memory_mb' in result.metadata
        assert result.metadata['has_cross_sectional'] is True
        assert set(result.metadata['unique_features']) == {'close', 'volume'}