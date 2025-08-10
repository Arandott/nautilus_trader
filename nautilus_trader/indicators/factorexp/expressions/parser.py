"""
Expression parser for converting FactorExp strings to AST.

This module provides a parser that converts FactorExp expression strings
into abstract syntax trees that can be evaluated by Nautilus Trader.
"""

import re
from typing import Optional, Tuple, List

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


class ParseError(Exception):
    """Raised when expression parsing fails."""
    pass


class ExpressionParser:
    """
    Parser for FactorExp expression strings.
    
    Converts expressions like "TS_Mean($close, 20) / TS_Std($close, 20)"
    into an abstract syntax tree that can be evaluated within Nautilus Trader.
    
    Supports:
    - Features: $close, $volume, $high, $low, etc.
    - Constants: numeric values
    - Arithmetic: +, -, *, /, ^
    - Unary operators: Log, Abs, Sign, etc.
    - Binary operators: Add, Sub, Mul, Div, Pow, etc.
    - Rolling operators: TS_Mean, TS_Std, TS_Min, TS_Max, etc.
    - Pair rolling operators: TS_Corr, TS_Cov
    - Cross-sectional operators: CSRank, Demean, ZScore
    """
    
    # Token patterns
    FEATURE_PATTERN = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
    NUMBER_PATTERN = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
    OPERATOR_PATTERN = r'[A-Z][A-Za-z_]*'
    
    # Operator categories
    UNARY_OPS = {
        'Log', 'Log10', 'Abs', 'Sign', 'Neg',
        'Sqrt', 'Exp', 'Sin', 'Cos', 'Tan',
        'Sinh', 'Cosh', 'Tanh', 'Asin', 'Acos', 'Atan',
        'TSFill', 'TSPctChg',
    }
    
    BINARY_OPS = {
        'Add', 'Sub', 'Mul', 'Div', 'Pow',
        'Greater', 'Less', 'GreaterEq', 'LessEq', 'Equal', 'NotEqual',
        'And', 'Or', 'Max', 'Min',
    }
    
    ROLLING_OPS = {
        'TS_Mean', 'TS_Sum', 'TS_Std', 'TS_Var', 'TS_Skew', 'TS_Kurt',
        'TS_Max', 'TS_Min', 'TS_Med', 'TS_Mad', 'TS_WMA', 'TS_EMA', 
        'TS_EMStd', 'TS_Delta', 'TS_Ref', 'TS_Rank', 'TS_Count',
        'TS_Argmax', 'TS_Argmin', 'TS_Product',
    }
    
    PAIR_ROLLING_OPS = {
        'TS_Cov', 'TS_Corr', 'TS_Beta',
    }
    
    CROSS_SECTIONAL_OPS = {
        'CSRank', 'CSMinMax', 'Demean', 'ZScore',
        'CSQuantile', 'CSMean', 'CSStd', 'CSSum',
    }
    
    def __init__(self):
        """Initialize the expression parser."""
        self._tokenizer = self._create_tokenizer()
        self._tokens = []
        self._pos = 0
    
    def parse(self, expression: str) -> Expression:
        """
        Parse an expression string into an AST.
        
        Parameters
        ----------
        expression : str
            The expression to parse (e.g., "TS_Mean($close, 20)")
            
        Returns
        -------
        Expression
            The parsed expression AST
            
        Raises
        ------
        ParseError
            If the expression is invalid or malformed
        """
        if not expression or not expression.strip():
            raise ParseError("Empty expression")
            
        # Clean expression
        expression = expression.strip()
        
        # Tokenize
        self._tokens = self._tokenize(expression)
        self._pos = 0
        
        if not self._tokens:
            raise ParseError("No valid tokens found in expression")
        
        try:
            # Parse the expression
            result = self._parse_expression()
            
            # Ensure all tokens are consumed
            if self._pos < len(self._tokens):
                remaining = self._tokens[self._pos]
                raise ParseError(f"Unexpected token: {remaining[1]} at position {self._pos}")
                
            return result
            
        except ParseError:
            raise
        except Exception as e:
            # Provide context for debugging
            current = self._current_token()
            if current:
                raise ParseError(f"Parse error at token '{current[1]}': {str(e)}")
            else:
                raise ParseError(f"Parse error: {str(e)}")
    
    def _create_tokenizer(self):
        """Create a regex tokenizer for the expression language."""
        patterns = [
            ('FEATURE', self.FEATURE_PATTERN),
            ('NUMBER', self.NUMBER_PATTERN),
            ('OPERATOR', self.OPERATOR_PATTERN),
            ('LPAREN', r'\('),
            ('RPAREN', r'\)'),
            ('COMMA', r','),
            ('PLUS', r'\+'),
            ('MINUS', r'-'),
            ('STAR', r'\*'),
            ('SLASH', r'/'),
            ('CARET', r'\^'),
            ('WHITESPACE', r'\s+'),
        ]
        
        pattern = '|'.join(f'(?P<{name}>{pattern})' for name, pattern in patterns)
        return re.compile(pattern)
    
    def _tokenize(self, expression: str) -> List[Tuple[str, str]]:
        """Tokenize the expression string."""
        tokens = []
        last_end = 0
        
        for match in self._tokenizer.finditer(expression):
            kind = match.lastgroup
            value = match.group()
            start = match.start()
            
            # Check for unmatched characters
            if start > last_end:
                unmatched = expression[last_end:start]
                if unmatched.strip():
                    raise ParseError(f"Invalid characters: '{unmatched}'")
            
            last_end = match.end()
            
            # Skip whitespace
            if kind == 'WHITESPACE':
                continue
                
            tokens.append((kind, value))
        
        # Check for trailing unmatched characters
        if last_end < len(expression):
            unmatched = expression[last_end:]
            if unmatched.strip():
                raise ParseError(f"Invalid trailing characters: '{unmatched}'")
            
        return tokens
    
    def _current_token(self) -> Optional[Tuple[str, str]]:
        """Get the current token without consuming it."""
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None
    
    def _peek_token(self, offset: int = 1) -> Optional[Tuple[str, str]]:
        """Peek at a future token without consuming it."""
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return None
    
    def _consume_token(self, expected_kind: Optional[str] = None) -> Tuple[str, str]:
        """Consume and return the current token."""
        if self._pos >= len(self._tokens):
            raise ParseError("Unexpected end of expression")
            
        kind, value = self._tokens[self._pos]
        
        if expected_kind and kind != expected_kind:
            raise ParseError(f"Expected {expected_kind}, got {value}")
            
        self._pos += 1
        return kind, value
    
    def _parse_expression(self) -> Expression:
        """Parse a complete expression with proper precedence."""
        return self._parse_additive()
    
    def _parse_additive(self) -> Expression:
        """Parse addition and subtraction (left-associative)."""
        left = self._parse_multiplicative()
        
        while True:
            token = self._current_token()
            if not token:
                break
                
            kind, _ = token
            if kind == 'PLUS':
                self._consume_token()
                right = self._parse_multiplicative()
                left = BinaryOp('Add', left, right)
            elif kind == 'MINUS':
                self._consume_token()
                right = self._parse_multiplicative()
                left = BinaryOp('Sub', left, right)
            else:
                break
                
        return left
    
    def _parse_multiplicative(self) -> Expression:
        """Parse multiplication and division (left-associative)."""
        left = self._parse_power()
        
        while True:
            token = self._current_token()
            if not token:
                break
                
            kind, _ = token
            if kind == 'STAR':
                self._consume_token()
                right = self._parse_power()
                left = BinaryOp('Mul', left, right)
            elif kind == 'SLASH':
                self._consume_token()
                right = self._parse_power()
                left = BinaryOp('Div', left, right)
            else:
                break
                
        return left
    
    def _parse_power(self) -> Expression:
        """Parse exponentiation (right-associative)."""
        left = self._parse_unary()
        
        token = self._current_token()
        if token and token[0] == 'CARET':
            self._consume_token()
            right = self._parse_power()  # Right associative
            return BinaryOp('Pow', left, right)
            
        return left
    
    def _parse_unary(self) -> Expression:
        """Parse unary operators."""
        token = self._current_token()
        
        if token and token[0] == 'MINUS':
            self._consume_token()
            operand = self._parse_unary()
            return UnaryOp('Neg', operand)
        elif token and token[0] == 'PLUS':
            self._consume_token()
            return self._parse_unary()
        
        return self._parse_primary()
    
    def _parse_primary(self) -> Expression:
        """Parse primary expressions (features, constants, function calls, parentheses)."""
        token = self._current_token()
        if not token:
            raise ParseError("Unexpected end of expression")
            
        kind, value = token
        
        # Feature
        if kind == 'FEATURE':
            self._consume_token()
            feature_name = value[1:]  # Remove $ prefix
            return Feature(feature_name)
        
        # Number
        elif kind == 'NUMBER':
            self._consume_token()
            # Handle scientific notation and convert to float
            try:
                num_value = float(value)
            except ValueError:
                raise ParseError(f"Invalid number: {value}")
            return Constant(num_value)
        
        # Function call or operator
        elif kind == 'OPERATOR':
            return self._parse_function_call()
        
        # Parenthesized expression
        elif kind == 'LPAREN':
            self._consume_token()
            expr = self._parse_expression()
            self._consume_token('RPAREN')
            return expr
        
        else:
            raise ParseError(f"Unexpected token: {value}")
    
    def _parse_function_call(self) -> Expression:
        """Parse a function call (operator with arguments)."""
        _, op_name = self._consume_token('OPERATOR')
        self._consume_token('LPAREN')
        
        # Parse arguments
        args = []
        while True:
            token = self._current_token()
            if token and token[0] == 'RPAREN':
                break
                
            args.append(self._parse_expression())
            
            token = self._current_token()
            if token and token[0] == 'COMMA':
                self._consume_token()
            elif token and token[0] == 'RPAREN':
                break
            else:
                raise ParseError("Expected comma or closing parenthesis")
        
        self._consume_token('RPAREN')
        
        # Create appropriate AST node based on operator type
        if op_name in self.UNARY_OPS:
            if len(args) != 1:
                raise ParseError(f"{op_name} expects 1 argument, got {len(args)}")
            return UnaryOp(op_name, args[0])
            
        elif op_name in self.BINARY_OPS:
            if len(args) != 2:
                raise ParseError(f"{op_name} expects 2 arguments, got {len(args)}")
            return BinaryOp(op_name, args[0], args[1])
            
        elif op_name in self.ROLLING_OPS:
            if len(args) != 2:
                raise ParseError(f"{op_name} expects 2 arguments (expression, window), got {len(args)}")
            
            # Second argument must be a constant integer
            if not isinstance(args[1], Constant):
                raise ParseError(f"{op_name} window must be a constant number")
            
            window = int(args[1].value)
            if window <= 0:
                raise ParseError(f"{op_name} window must be positive, got {window}")
                
            return RollingOp(op_name, args[0], window)
            
        elif op_name in self.PAIR_ROLLING_OPS:
            if len(args) != 3:
                raise ParseError(f"{op_name} expects 3 arguments (expr1, expr2, window), got {len(args)}")
            
            # Third argument must be a constant integer
            if not isinstance(args[2], Constant):
                raise ParseError(f"{op_name} window must be a constant number")
            
            window = int(args[2].value)
            if window <= 0:
                raise ParseError(f"{op_name} window must be positive, got {window}")
                
            return PairRollingOp(op_name, args[0], args[1], window)
            
        elif op_name in self.CROSS_SECTIONAL_OPS:
            if len(args) != 1:
                raise ParseError(f"{op_name} expects 1 argument, got {len(args)}")
            return CrossSectionalOp(op_name, args[0])
            
        else:
            raise ParseError(f"Unknown operator: {op_name}")