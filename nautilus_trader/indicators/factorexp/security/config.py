"""
Security configuration for FactorExp expression execution.

This module provides security settings to ensure safe execution of
user-defined factor expressions within Nautilus Trader.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Set, Optional, Dict


class SecurityLevel(Enum):
    """Predefined security levels for different use cases."""
    
    TRUSTED = "trusted"      # Minimal checks for trusted expressions
    STANDARD = "standard"    # Default security for general use
    PARANOID = "paranoid"    # Maximum security for untrusted expressions


@dataclass
class SecurityConfig:
    """
    Configuration for security constraints on expression execution.
    
    Provides comprehensive security settings including resource limits,
    operator whitelisting, and execution sandboxing.
    
    Attributes
    ----------
    level : SecurityLevel
        Security level preset (default: STANDARD)
    max_memory_mb : int
        Maximum memory usage in megabytes (default: 100)
    max_cpu_ms : int
        Maximum CPU time in milliseconds per evaluation (default: 10)
    max_expression_depth : int
        Maximum nesting depth for expressions (default: 10)
    max_window_size : int
        Maximum size for rolling windows (default: 5000)
    max_features : int
        Maximum number of unique features (default: 50)
    max_operators : int
        Maximum number of operators in expression (default: 100)
    allowed_operators : Set[str], optional
        Whitelist of allowed operators (None = use defaults)
    forbidden_features : Set[str], optional
        Blacklist of forbidden feature names (None = use defaults)
    enable_sandboxing : bool
        Whether to enable sandboxed execution (default: True)
    enable_audit_log : bool
        Whether to log all operations for audit (default: False)
    enable_caching : bool
        Whether to cache parsed expressions (default: True)
    cache_size : int
        Maximum number of cached expressions (default: 1000)
    """
    
    level: SecurityLevel = SecurityLevel.STANDARD
    max_memory_mb: int = 100
    max_cpu_ms: int = 10
    max_expression_depth: int = 10
    max_window_size: int = 5000
    max_features: int = 50
    max_operators: int = 100
    allowed_operators: Optional[Set[str]] = None
    forbidden_features: Optional[Set[str]] = None
    enable_sandboxing: bool = True
    enable_audit_log: bool = False
    enable_caching: bool = True
    cache_size: int = 1000
    
    # Security level presets
    LEVEL_PRESETS: Dict[SecurityLevel, dict] = field(default_factory=lambda: {
        SecurityLevel.TRUSTED: {
            'max_memory_mb': 500,
            'max_cpu_ms': 100,
            'max_expression_depth': 20,
            'max_window_size': 10000,
            'max_features': 100,
            'max_operators': 200,
            'enable_sandboxing': False,
        },
        SecurityLevel.STANDARD: {
            'max_memory_mb': 100,
            'max_cpu_ms': 10,
            'max_expression_depth': 10,
            'max_window_size': 5000,
            'max_features': 50,
            'max_operators': 100,
            'enable_sandboxing': True,
        },
        SecurityLevel.PARANOID: {
            'max_memory_mb': 20,
            'max_cpu_ms': 5,
            'max_expression_depth': 5,
            'max_window_size': 1000,
            'max_features': 20,
            'max_operators': 50,
            'enable_sandboxing': True,
            'enable_audit_log': True,
        },
    })
    
    def __post_init__(self):
        """Apply security level presets and validate configuration."""
        # Apply level presets if using a security level
        if self.level in self.LEVEL_PRESETS:
            preset = self.LEVEL_PRESETS[self.level]
            for key, value in preset.items():
                if key in self.__dict__ and self.__dict__[key] == self.__class__.__dataclass_fields__[key].default:
                    setattr(self, key, value)
        
        # Validate all parameters
        if self.max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be positive")
        if self.max_cpu_ms <= 0:
            raise ValueError("max_cpu_ms must be positive")
        if self.max_expression_depth <= 0:
            raise ValueError("max_expression_depth must be positive")
        if self.max_window_size <= 0:
            raise ValueError("max_window_size must be positive")
        if self.max_features <= 0:
            raise ValueError("max_features must be positive")
        if self.max_operators <= 0:
            raise ValueError("max_operators must be positive")
        if self.cache_size < 0:
            raise ValueError("cache_size must be non-negative")
            
        # Set default allowed operators if not specified
        if self.allowed_operators is None:
            self.allowed_operators = self._get_default_allowed_operators()
            
        # Set default forbidden features if not specified
        if self.forbidden_features is None:
            self.forbidden_features = self._get_default_forbidden_features()
    
    def _get_default_allowed_operators(self) -> Set[str]:
        """Get the default set of allowed operators based on security level."""
        base_operators = {
            # Basic arithmetic
            "Add", "Sub", "Mul", "Div",
            # Basic unary
            "Abs", "Sign", "Neg",
            # Basic rolling
            "TS_Mean", "TS_Sum", "TS_Max", "TS_Min",
            "TS_Std", "TS_Var",
            # Basic comparison
            "Greater", "Less", "Equal",
        }
        
        standard_operators = base_operators | {
            # Extended arithmetic
            "Pow", "Sqrt",
            # Extended unary
            "Log", "Log10", "Exp",
            # Extended rolling
            "TS_Med", "TS_Mad", "TS_EMA", "TS_WMA",
            "TS_Skew", "TS_Kurt", "TS_Rank",
            "TS_Delta", "TS_Ref", "TS_Count",
            # Pair operations
            "TS_Cov", "TS_Corr",
            # Cross-sectional
            "CSRank", "Demean", "ZScore",
            # Extended comparison
            "GreaterEq", "LessEq", "NotEqual",
            "And", "Or", "Max", "Min",
        }
        
        trusted_operators = standard_operators | {
            # Advanced math
            "Sin", "Cos", "Tan", "Asin", "Acos", "Atan",
            "Sinh", "Cosh", "Tanh",
            # Advanced rolling
            "TS_Argmax", "TS_Argmin", "TS_Product",
            "TS_EMStd", "TS_Beta",
            # Advanced cross-sectional
            "CSMinMax", "CSQuantile", "CSMean", "CSStd", "CSSum",
            # Special operations
            "TSFill", "TSPctChg",
        }
        
        if self.level == SecurityLevel.PARANOID:
            return base_operators
        elif self.level == SecurityLevel.STANDARD:
            return standard_operators
        else:  # TRUSTED
            return trusted_operators
    
    def _get_default_forbidden_features(self) -> Set[str]:
        """Get the default set of forbidden feature names."""
        base_forbidden = {
            # Python internals
            "__class__", "__module__", "__dict__", "__init__",
            "__new__", "__del__", "__repr__", "__str__",
            "__getattr__", "__setattr__", "__delattr__",
            "__getitem__", "__setitem__", "__delitem__",
            # Dangerous functions
            "eval", "exec", "compile", "open", "input",
            "import", "__import__", "globals", "locals",
            "vars", "dir", "help", "type", "isinstance",
            # File system
            "file", "read", "write", "close", "flush",
            # Network
            "socket", "urllib", "requests", "http",
            # OS interaction
            "os", "sys", "subprocess", "shutil",
        }
        
        if self.level == SecurityLevel.PARANOID:
            # Add more restrictions for paranoid mode
            return base_forbidden | {
                # Any double underscore
                "__", "getattr", "setattr", "delattr",
                "property", "classmethod", "staticmethod",
            }
        else:
            return base_forbidden
    
    def is_operator_allowed(self, operator: str) -> bool:
        """
        Check if an operator is allowed.
        
        Parameters
        ----------
        operator : str
            The operator name to check
            
        Returns
        -------
        bool
            True if the operator is allowed
        """
        return operator in self.allowed_operators
    
    def is_feature_allowed(self, feature: str) -> bool:
        """
        Check if a feature name is allowed.
        
        Parameters
        ----------
        feature : str
            The feature name to check
            
        Returns
        -------
        bool
            True if the feature is allowed
        """
        # Check against forbidden list
        if feature in self.forbidden_features:
            return False
        
        # Check for patterns in paranoid mode
        if self.level == SecurityLevel.PARANOID:
            if '__' in feature or '..' in feature:
                return False
            if any(char in feature for char in ['/', '\\', '\x00', '\n', '\r']):
                return False
        
        return True
    
    @classmethod
    def trusted(cls) -> 'SecurityConfig':
        """Create a trusted security configuration."""
        return cls(level=SecurityLevel.TRUSTED)
    
    @classmethod
    def standard(cls) -> 'SecurityConfig':
        """Create a standard security configuration."""
        return cls(level=SecurityLevel.STANDARD)
    
    @classmethod
    def paranoid(cls) -> 'SecurityConfig':
        """Create a paranoid security configuration."""
        return cls(level=SecurityLevel.PARANOID)