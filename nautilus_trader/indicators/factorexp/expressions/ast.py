"""
Abstract Syntax Tree classes for factor expressions.

This module defines the AST structure for representing FactorExp expressions
in a way that can be efficiently evaluated within Nautilus Trader.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Union
from dataclasses import dataclass


class Expression(ABC):
    """Base class for all expression nodes in the factor expression AST."""
    
    @abstractmethod
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        """Accept a visitor for the visitor pattern implementation."""
        pass
    
    @abstractmethod
    def get_depth(self) -> int:
        """Get the maximum depth of this expression tree."""
        pass
    
    @abstractmethod
    def get_features(self) -> List[str]:
        """Get all feature names used in this expression."""
        pass
    
    @abstractmethod
    def get_operators(self) -> List[str]:
        """Get all operators used in this expression."""
        pass


@dataclass
class Feature(Expression):
    """Represents a data feature (e.g., $close, $volume, $high, $low)."""
    
    name: str
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_feature(self)
    
    def get_depth(self) -> int:
        return 1
    
    def get_features(self) -> List[str]:
        return [self.name]
    
    def get_operators(self) -> List[str]:
        return []
    
    def __str__(self) -> str:
        return f"${self.name}"


@dataclass
class Constant(Expression):
    """Represents a constant numeric value."""
    
    value: Union[int, float]
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_constant(self)
    
    def get_depth(self) -> int:
        return 1
    
    def get_features(self) -> List[str]:
        return []
    
    def get_operators(self) -> List[str]:
        return []
    
    def __str__(self) -> str:
        return str(self.value)


@dataclass
class UnaryOp(Expression):
    """Represents a unary operation (e.g., Log, Abs, Neg, Sign)."""
    
    operator: str
    operand: Expression
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_unary_op(self)
    
    def get_depth(self) -> int:
        return 1 + self.operand.get_depth()
    
    def get_features(self) -> List[str]:
        return self.operand.get_features()
    
    def get_operators(self) -> List[str]:
        return [self.operator] + self.operand.get_operators()
    
    def __str__(self) -> str:
        return f"{self.operator}({self.operand})"


@dataclass
class BinaryOp(Expression):
    """Represents a binary operation (e.g., Add, Sub, Mul, Div, Pow)."""
    
    operator: str
    left: Expression
    right: Expression
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_binary_op(self)
    
    def get_depth(self) -> int:
        return 1 + max(self.left.get_depth(), self.right.get_depth())
    
    def get_features(self) -> List[str]:
        features = []
        features.extend(self.left.get_features())
        features.extend(self.right.get_features())
        return features
    
    def get_operators(self) -> List[str]:
        operators = [self.operator]
        operators.extend(self.left.get_operators())
        operators.extend(self.right.get_operators())
        return operators
    
    def __str__(self) -> str:
        # Handle infix operators specially for readability
        if self.operator in ["Add", "Sub", "Mul", "Div", "Pow"]:
            op_symbols = {"Add": "+", "Sub": "-", "Mul": "*", "Div": "/", "Pow": "**"}
            return f"({self.left} {op_symbols[self.operator]} {self.right})"
        return f"{self.operator}({self.left}, {self.right})"


@dataclass
class RollingOp(Expression):
    """Represents a rolling window operation (e.g., TS_Mean, TS_Std, TS_Min, TS_Max)."""
    
    operator: str
    operand: Expression
    window: int
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_rolling_op(self)
    
    def get_depth(self) -> int:
        return 1 + self.operand.get_depth()
    
    def get_features(self) -> List[str]:
        return self.operand.get_features()
    
    def get_operators(self) -> List[str]:
        return [self.operator] + self.operand.get_operators()
    
    def __str__(self) -> str:
        return f"{self.operator}({self.operand}, {self.window})"


@dataclass 
class PairRollingOp(Expression):
    """Represents a pair rolling operation (e.g., TS_Corr, TS_Cov)."""
    
    operator: str
    left: Expression
    right: Expression
    window: int
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_pair_rolling_op(self)
    
    def get_depth(self) -> int:
        return 1 + max(self.left.get_depth(), self.right.get_depth())
    
    def get_features(self) -> List[str]:
        features = []
        features.extend(self.left.get_features())
        features.extend(self.right.get_features())
        return features
    
    def get_operators(self) -> List[str]:
        operators = [self.operator]
        operators.extend(self.left.get_operators())
        operators.extend(self.right.get_operators())
        return operators
    
    def __str__(self) -> str:
        return f"{self.operator}({self.left}, {self.right}, {self.window})"


@dataclass
class CrossSectionalOp(Expression):
    """Represents a cross-sectional operation (e.g., CSRank, Demean, ZScore)."""
    
    operator: str
    operand: Expression
    
    def accept(self, visitor: 'ExpressionVisitor') -> Any:
        return visitor.visit_cross_sectional_op(self)
    
    def get_depth(self) -> int:
        return 1 + self.operand.get_depth()
    
    def get_features(self) -> List[str]:
        return self.operand.get_features()
    
    def get_operators(self) -> List[str]:
        return [self.operator] + self.operand.get_operators()
    
    def __str__(self) -> str:
        return f"{self.operator}({self.operand})"


class ExpressionVisitor(ABC):
    """Visitor interface for traversing expression trees.
    
    This implements the visitor pattern, allowing different operations
    to be performed on the expression tree without modifying the tree classes.
    """
    
    @abstractmethod
    def visit_feature(self, expr: Feature) -> Any:
        """Visit a feature node."""
        pass
    
    @abstractmethod
    def visit_constant(self, expr: Constant) -> Any:
        """Visit a constant node."""
        pass
    
    @abstractmethod
    def visit_unary_op(self, expr: UnaryOp) -> Any:
        """Visit a unary operation node."""
        pass
    
    @abstractmethod
    def visit_binary_op(self, expr: BinaryOp) -> Any:
        """Visit a binary operation node."""
        pass
    
    @abstractmethod
    def visit_rolling_op(self, expr: RollingOp) -> Any:
        """Visit a rolling operation node."""
        pass
    
    @abstractmethod
    def visit_pair_rolling_op(self, expr: PairRollingOp) -> Any:
        """Visit a pair rolling operation node."""
        pass
    
    @abstractmethod
    def visit_cross_sectional_op(self, expr: CrossSectionalOp) -> Any:
        """Visit a cross-sectional operation node."""
        pass