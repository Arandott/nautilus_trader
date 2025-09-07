"""
Test cases for conditional operators in FactorExp.

Tests the When, And, and Or operators functionality.
"""

from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
from nautilus_trader.indicators.factorexp.expressions.ast import BinaryOp


class TestConditionalOperators:
    """Test cases for conditional operators."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ExpressionParser()
    
    def test_when_operator_parsing(self):
        """Test that When operator is correctly parsed."""
        # Parse a When expression
        expr_str = "When(Greater($volume, 1000), $close)"
        expr = self.parser.parse(expr_str)
        
        # Verify the structure
        assert isinstance(expr, BinaryOp)
        assert expr.name == "When"
        assert len(expr.args) == 2
        
        # The first argument should be the condition
        condition = expr.args[0]
        assert isinstance(condition, BinaryOp)
        assert condition.name == "Greater"
        
        # The second argument should be the operand
        operand = expr.args[1]
        assert operand.name == "$close"
    
    def test_and_operator_parsing(self):
        """Test that And operator is correctly parsed."""
        # Parse an And expression
        expr_str = "And(Greater($close, 100), Greater($volume, 1000))"
        expr = self.parser.parse(expr_str)
        
        # Verify the structure
        assert isinstance(expr, BinaryOp)
        assert expr.name == "And"
        assert len(expr.args) == 2
        
        # Both arguments should be Greater comparisons
        arg1 = expr.args[0]
        assert isinstance(arg1, BinaryOp)
        assert arg1.name == "Greater"
        
        arg2 = expr.args[1]
        assert isinstance(arg2, BinaryOp)
        assert arg2.name == "Greater"
    
    def test_or_operator_parsing(self):
        """Test that Or operator is correctly parsed."""
        # Parse an Or expression
        expr_str = "Or(Greater($close, 100), Less($volume, 500))"
        expr = self.parser.parse(expr_str)
        
        # Verify the structure
        assert isinstance(expr, BinaryOp)
        assert expr.name == "Or"
        assert len(expr.args) == 2
        
        # Check the arguments
        arg1 = expr.args[0]
        assert isinstance(arg1, BinaryOp)
        assert arg1.name == "Greater"
        
        arg2 = expr.args[1]
        assert isinstance(arg2, BinaryOp)
        assert arg2.name == "Less"
    
    def test_complex_conditional_expression(self):
        """Test a complex expression with multiple conditional operators."""
        # Complex expression: When volume is high AND price is rising, return close, otherwise NaN
        expr_str = "When(And(Greater($volume, 10000), Greater($close, $open)), $close)"
        expr = self.parser.parse(expr_str)
        
        # Verify the root is When
        assert isinstance(expr, BinaryOp)
        assert expr.name == "When"
        
        # The condition should be an And
        condition = expr.args[0]
        assert isinstance(condition, BinaryOp)
        assert condition.name == "And"
        
        # The And should have two Greater comparisons
        and_arg1 = condition.args[0]
        assert isinstance(and_arg1, BinaryOp)
        assert and_arg1.name == "Greater"
        
        and_arg2 = condition.args[1]
        assert isinstance(and_arg2, BinaryOp)
        assert and_arg2.name == "Greater"
    
    def test_nested_when_operators(self):
        """Test nested When operators for multi-condition logic."""
        # Nested When: different values based on multiple conditions
        expr_str = "When(Greater($volume, 10000), When(Greater($close, 100), Mul($close, 2), $close))"
        expr = self.parser.parse(expr_str)
        
        # Verify the outer When
        assert isinstance(expr, BinaryOp)
        assert expr.name == "When"
        
        # The second argument should be another When
        inner_when = expr.args[1]
        assert isinstance(inner_when, BinaryOp)
        assert inner_when.name == "When"
    
    def test_when_with_rolling_operators(self):
        """Test When operator with rolling operators."""
        # When moving average crosses above price, signal
        expr_str = "When(Greater(TS_Mean($close, 20), $close), 1)"
        expr = self.parser.parse(expr_str)
        
        # Verify structure
        assert isinstance(expr, BinaryOp)
        assert expr.name == "When"
        
        # The condition should be a Greater with TS_Mean
        condition = expr.args[0]
        assert isinstance(condition, BinaryOp)
        assert condition.name == "Greater"
        
        # First arg of Greater should be TS_Mean
        ts_mean = condition.args[0]
        assert ts_mean.name == "TS_Mean"


# Example usage demonstrations
def example_conditional_expressions():
    """
    Example expressions using conditional operators.
    
    These examples show how to use When, And, and Or operators
    in FactorExp expressions for creating trading signals.
    """
    
    # Example 1: Volume filter - only calculate when volume is significant
    volume_filter = "When(Greater($volume, 10000), $close)"
    
    # Example 2: Bullish signal - price above MA AND volume increasing
    bullish_signal = "And(Greater($close, TS_Mean($close, 20)), Greater($volume, TS_Mean($volume, 10)))"
    
    # Example 3: Entry condition - either breakout OR reversal
    entry_condition = "Or(Greater($close, TS_Max($high, 20)), Less($close, Mul(TS_Min($low, 20), 0.98)))"
    
    # Example 4: Conditional indicator - different calculations based on market condition
    conditional_indicator = """
    When(
        Greater($volume, TS_Mean($volume, 20)),
        Div($close, TS_Mean($close, 10)),
        Div($close, TS_Mean($close, 50))
    )
    """
    
    # Example 5: Multi-condition filter using nested logic
    complex_filter = """
    When(
        And(
            Greater($close, 50),
            Or(
                Greater($volume, 100000),
                Greater(TS_Std($close, 20), 2)
            )
        ),
        Mul($close, 1.01)
    )
    """
    
    # Example 6: Regime detection - different behavior in trending vs ranging markets
    regime_based = """
    When(
        Greater(Abs(TS_Beta($close, $market, 60)), 0.8),
        TS_Mean($close, 10),
        TS_Mean($close, 50)
    )
    """
    
    return {
        "volume_filter": volume_filter,
        "bullish_signal": bullish_signal,
        "entry_condition": entry_condition,
        "conditional_indicator": conditional_indicator,
        "complex_filter": complex_filter,
        "regime_based": regime_based,
    }


if __name__ == "__main__":
    # Run basic tests
    test = TestConditionalOperators()
    test.setup_method()
    
    print("Testing When operator parsing...")
    test.test_when_operator_parsing()
    print("✓ When operator parsing successful")
    
    print("Testing And operator parsing...")
    test.test_and_operator_parsing()
    print("✓ And operator parsing successful")
    
    print("Testing Or operator parsing...")
    test.test_or_operator_parsing()
    print("✓ Or operator parsing successful")
    
    print("\nExample conditional expressions:")
    examples = example_conditional_expressions()
    for name, expr in examples.items():
        print(f"\n{name}:\n{expr}")
    
    print("\n✓ All conditional operator tests passed!")