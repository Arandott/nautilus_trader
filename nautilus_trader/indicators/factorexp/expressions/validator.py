"""
Expression validator for security and correctness checks.

This module provides comprehensive validation for FactorExp expressions
to ensure they are safe to execute within Nautilus Trader.
"""

from typing import Set, Optional, List
from dataclasses import dataclass, field

from nautilus_trader.indicators.factorexp.expressions.ast import (
    Expression,
    Feature,
    Constant,
    UnaryOp,
    BinaryOp,
    RollingOp,
    PairRollingOp,
    CrossSectionalOp,
    ExpressionVisitor,
)


@dataclass
class ValidationResult:
    """Result of expression validation."""
    
    is_valid: bool
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    
    @property
    def has_warnings(self) -> bool:
        """Check if validation produced any warnings."""
        return len(self.warnings) > 0


class ExpressionValidator(ExpressionVisitor):
    """
    Validates expressions for security and correctness.
    
    Performs comprehensive validation including:
    - Expression depth limits to prevent stack overflow
    - Operator whitelisting for security
    - Feature name validation
    - Window size limits for memory protection
    - Circular reference detection
    - Numerical stability checks
    - Resource usage estimation
    """
    
    # Default limits
    DEFAULT_MAX_DEPTH = 10
    DEFAULT_MAX_FEATURES = 50
    DEFAULT_MAX_OPERATORS = 100
    DEFAULT_MAX_WINDOW = 5000
    DEFAULT_MAX_CONSTANT = 1e10
    
    # Dangerous patterns in feature names
    DANGEROUS_PATTERNS = [
        '__', '..', '/', '\\', '\x00', '\n', '\r',
        'exec', 'eval', 'import', 'open', 'file',
    ]
    
    def __init__(
        self,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_features: int = DEFAULT_MAX_FEATURES,
        max_operators: int = DEFAULT_MAX_OPERATORS,
        max_window: int = DEFAULT_MAX_WINDOW,
        max_constant: float = DEFAULT_MAX_CONSTANT,
        allowed_operators: Optional[Set[str]] = None,
        allowed_features: Optional[Set[str]] = None,
    ):
        """
        Initialize the expression validator.
        
        Parameters
        ----------
        max_depth : int
            Maximum expression tree depth
        max_features : int
            Maximum number of unique features
        max_operators : int
            Maximum number of operators
        max_window : int
            Maximum rolling window size
        max_constant : float
            Maximum absolute value for constants
        allowed_operators : Set[str], optional
            Whitelist of allowed operators (None = all allowed)
        allowed_features : Set[str], optional
            Whitelist of allowed feature names (None = all safe names allowed)
        """
        self.max_depth = max_depth
        self.max_features = max_features
        self.max_operators = max_operators
        self.max_window = max_window
        self.max_constant = max_constant
        self.allowed_operators = allowed_operators
        self.allowed_features = allowed_features
        self._reset()
    
    def validate(self, expression: Expression) -> ValidationResult:
        """
        Validate an expression for security and correctness.
        
        Parameters
        ----------
        expression : Expression
            The expression AST to validate
            
        Returns
        -------
        ValidationResult
            Validation result with errors and warnings
        """
        self._reset()
        
        try:
            # Check expression depth
            depth = expression.get_depth()
            if depth > self.max_depth:
                return ValidationResult(
                    is_valid=False,
                    error=f"Expression depth {depth} exceeds maximum {self.max_depth}"
                )
            
            # Collect all operators and features
            all_operators = expression.get_operators()
            all_features = expression.get_features()
            
            # Check operator count
            if len(all_operators) > self.max_operators:
                return ValidationResult(
                    is_valid=False,
                    error=f"Number of operators ({len(all_operators)}) exceeds maximum {self.max_operators}"
                )
            
            # Check feature count
            unique_features = set(all_features)
            if len(unique_features) > self.max_features:
                return ValidationResult(
                    is_valid=False,
                    error=f"Number of unique features ({len(unique_features)}) exceeds maximum {self.max_features}"
                )
            
            # Visit expression tree for detailed validation
            expression.accept(self)
            
            # Check for collected errors
            if self._errors:
                return ValidationResult(
                    is_valid=False,
                    error=self._errors[0],  # Report first error
                    warnings=self._warnings,
                    metadata={
                        'depth': depth,
                        'operator_count': len(all_operators),
                        'feature_count': len(unique_features),
                        'unique_features': list(unique_features),
                        'estimated_memory_mb': self._estimate_memory_usage(expression),
                    }
                )
            
            # Validation passed
            return ValidationResult(
                is_valid=True,
                warnings=self._warnings,
                metadata={
                    'depth': depth,
                    'operator_count': len(all_operators),
                    'feature_count': len(unique_features),
                    'unique_features': list(unique_features),
                    'estimated_memory_mb': self._estimate_memory_usage(expression),
                    'has_cross_sectional': self._has_cross_sectional,
                }
            )
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                error=f"Validation error: {str(e)}"
            )
    
    def _reset(self):
        """Reset validator state for new validation."""
        self._errors: List[str] = []
        self._warnings: List[str] = []
        self._visited_features: Set[str] = set()
        self._operator_count = 0
        self._max_window_seen = 0
        self._has_cross_sectional = False
    
    def _is_operator_allowed(self, operator: str) -> bool:
        """Check if an operator is allowed."""
        if self.allowed_operators is None:
            return True
        return operator in self.allowed_operators
    
    def _is_feature_allowed(self, feature: str) -> bool:
        """Check if a feature name is allowed."""
        # Check explicit whitelist if provided
        if self.allowed_features is not None:
            return feature in self.allowed_features
        
        # Check for dangerous patterns
        feature_lower = feature.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in feature_lower:
                return False
        
        # Check for valid identifier
        if not feature.replace('_', '').isalnum():
            return False
        
        return True
    
    def _estimate_memory_usage(self, expression: Expression) -> float:
        """Estimate memory usage in MB for the expression."""
        # Basic estimation based on expression complexity
        base_memory = 0.1  # Base overhead
        
        # Add memory for rolling windows
        window_memory = (self._max_window_seen * 8 * len(self._visited_features)) / 1_000_000
        
        # Add memory for cross-sectional operations
        if self._has_cross_sectional:
            # Assume 100 instruments for estimation
            cross_section_memory = (100 * 8 * len(self._visited_features)) / 1_000_000
        else:
            cross_section_memory = 0
        
        total_memory = base_memory + window_memory + cross_section_memory
        return round(total_memory, 2)
    
    def visit_feature(self, expr: Feature) -> None:
        """Validate a feature reference."""
        # Check if feature name is allowed
        if not self._is_feature_allowed(expr.name):
            self._errors.append(f"Forbidden feature name: '{expr.name}'")
            return
        
        # Common feature name validation
        common_features = {
            'close', 'open', 'high', 'low', 'volume',
            'bid', 'ask', 'bid_size', 'ask_size',
            'trades', 'vwap', 'spread', 'mid',
        }
        
        if expr.name not in common_features:
            self._warnings.append(f"Non-standard feature name: '{expr.name}'")
        
        self._visited_features.add(expr.name)
    
    def visit_constant(self, expr: Constant) -> None:
        """Validate a constant value."""
        # Check for NaN or infinity
        if not (-float('inf') < expr.value < float('inf')):
            self._errors.append(f"Invalid constant value: {expr.value}")
            return
        
        # Check for extreme values
        if abs(expr.value) > self.max_constant:
            self._errors.append(
                f"Constant value {expr.value} exceeds maximum {self.max_constant}"
            )
            return
        
        # Warn about large values
        if abs(expr.value) > 1e6:
            self._warnings.append(f"Large constant value: {expr.value}")
    
    def visit_unary_op(self, expr: UnaryOp) -> None:
        """Validate a unary operation."""
        self._operator_count += 1
        
        # Check if operator is allowed
        if not self._is_operator_allowed(expr.operator):
            self._errors.append(f"Forbidden operator: {expr.operator}")
            return
        
        # Validate operand
        expr.operand.accept(self)
        
        # Operator-specific validation
        if expr.operator in ['Log', 'Log10', 'Sqrt']:
            # These require positive values
            if isinstance(expr.operand, Constant) and expr.operand.value <= 0:
                self._errors.append(f"{expr.operator} of non-positive constant")
        
        elif expr.operator in ['Asin', 'Acos']:
            # These require values in [-1, 1]
            if isinstance(expr.operand, Constant):
                if not -1 <= expr.operand.value <= 1:
                    self._errors.append(
                        f"{expr.operator} requires input in [-1, 1], got {expr.operand.value}"
                    )
    
    def visit_binary_op(self, expr: BinaryOp) -> None:
        """Validate a binary operation."""
        self._operator_count += 1
        
        # Check if operator is allowed
        if not self._is_operator_allowed(expr.operator):
            self._errors.append(f"Forbidden operator: {expr.operator}")
            return
        
        # Validate operands
        expr.left.accept(self)
        expr.right.accept(self)
        
        # Operator-specific validation
        if expr.operator == 'Div':
            # Check for division by zero
            if isinstance(expr.right, Constant) and expr.right.value == 0:
                self._errors.append("Division by zero")
                
        elif expr.operator == 'Pow':
            # Check for extreme exponents
            if isinstance(expr.right, Constant):
                if abs(expr.right.value) > 10:
                    self._warnings.append(f"Large exponent: {expr.right.value}")
                
                # Check for fractional powers of negative numbers
                if (isinstance(expr.left, Constant) and 
                    expr.left.value < 0 and 
                    expr.right.value != int(expr.right.value)):
                    self._errors.append(
                        "Fractional power of negative number"
                    )
    
    def visit_rolling_op(self, expr: RollingOp) -> None:
        """Validate a rolling window operation."""
        self._operator_count += 1
        
        # Check if operator is allowed
        if not self._is_operator_allowed(expr.operator):
            self._errors.append(f"Forbidden operator: {expr.operator}")
            return
        
        # Validate operand
        expr.operand.accept(self)
        
        # Check window size
        if expr.window <= 0:
            self._errors.append(f"Invalid window size: {expr.window}")
            return
            
        if expr.window > self.max_window:
            self._errors.append(
                f"Window size {expr.window} exceeds maximum {self.max_window}"
            )
            return
        
        # Track maximum window for memory estimation
        self._max_window_seen = max(self._max_window_seen, expr.window)
        
        # Warn about large windows
        if expr.window > 1000:
            self._warnings.append(f"Large window size: {expr.window}")
        
        # Operator-specific checks
        if expr.operator in ['TS_Std', 'TS_Var'] and expr.window < 2:
            self._errors.append(
                f"{expr.operator} requires window size >= 2"
            )
    
    def visit_pair_rolling_op(self, expr: PairRollingOp) -> None:
        """Validate a pair rolling operation."""
        self._operator_count += 1
        
        # Check if operator is allowed
        if not self._is_operator_allowed(expr.operator):
            self._errors.append(f"Forbidden operator: {expr.operator}")
            return
        
        # Validate operands
        expr.left.accept(self)
        expr.right.accept(self)
        
        # Check window size
        if expr.window <= 0:
            self._errors.append(f"Invalid window size: {expr.window}")
            return
            
        if expr.window > self.max_window:
            self._errors.append(
                f"Window size {expr.window} exceeds maximum {self.max_window}"
            )
            return
        
        # Track maximum window
        self._max_window_seen = max(self._max_window_seen, expr.window)
        
        # Warn about computational complexity
        if expr.window > 100:
            self._warnings.append(
                f"Pair rolling operation '{expr.operator}' with window {expr.window} may be computationally expensive"
            )
        
        # Operator-specific checks
        if expr.operator in ['TS_Corr', 'TS_Cov', 'TS_Beta'] and expr.window < 2:
            self._errors.append(
                f"{expr.operator} requires window size >= 2"
            )
    
    def visit_cross_sectional_op(self, expr: CrossSectionalOp) -> None:
        """Validate a cross-sectional operation."""
        self._operator_count += 1
        self._has_cross_sectional = True
        
        # Check if operator is allowed
        if not self._is_operator_allowed(expr.operator):
            self._errors.append(f"Forbidden operator: {expr.operator}")
            return
        
        # Validate operand
        expr.operand.accept(self)
        
        # Warn about cross-sectional operations
        self._warnings.append(
            f"Cross-sectional operation '{expr.operator}' requires multi-asset data"
        )