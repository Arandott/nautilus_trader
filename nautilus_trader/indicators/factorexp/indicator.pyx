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
FactorExp indicator implementation using high-performance Rust backend.

This module provides the Cython wrapper for the Rust-based FactorExpIndicator,
enabling expression-based factor computation with native performance.
"""

from typing import Optional

from libc.stdint cimport uint64_t

from nautilus_trader.core.correctness cimport Condition
from nautilus_trader.core.rust.model cimport PriceType
from nautilus_trader.indicators.base.indicator cimport Indicator
from nautilus_trader.model.data cimport Bar
from nautilus_trader.model.data cimport QuoteTick
from nautilus_trader.model.data cimport TradeTick

# Import Rust implementation from PyO3
# This will be available after the Rust code is compiled
try:
    from nautilus_trader.core.nautilus_pyo3.factorexp import FactorExpIndicator as RustFactorExpIndicator
except ImportError:
    # Fallback for development/testing when Rust module not yet compiled
    RustFactorExpIndicator = None


cdef class FactorExpIndicator(Indicator):
    """
    An indicator that evaluates FactorExp expressions on streaming market data.
    
    This indicator provides a high-performance bridge between FactorExp's expression
    language and Nautilus Trader's indicator framework, with all computations
    performed in Rust.
    
    Parameters
    ----------
    expression : str
        The FactorExp expression to evaluate (e.g., "TS_Mean($close, 20)")
    period : int, optional
        The maximum lookback period required by the expression (auto-detected if not provided)
    price_type : PriceType, default=PriceType.LAST
        The price type to use for quote tick data
    name : str, optional
        Custom name for the indicator (defaults to the expression)
    
    Raises
    ------
    ValueError
        If the expression cannot be parsed or compiled
    RuntimeError
        If the Rust module is not available
    
    Examples
    --------
    >>> # Simple moving average ratio
    >>> indicator = FactorExpIndicator("TS_Mean($close, 20) / TS_Mean($close, 50)")
    
    >>> # RSI approximation
    >>> indicator = FactorExpIndicator(
    ...     "100 - 100 / (1 + TS_Mean(Max($close - Delay($close, 1), 0), 14) / TS_Mean(Max(Delay($close, 1) - $close, 0), 14))",
    ...     name="RSI_Approx"
    ... )
    
    >>> # Bollinger Band width
    >>> indicator = FactorExpIndicator(
    ...     "2 * TS_Std($close, 20)",
    ...     name="BBWidth"
    ... )
    """
    cdef object _rust_indicator
    cdef str _expression
    cdef str _name
    cdef readonly int period
    cdef readonly double value
    cdef readonly uint64_t count
    cdef readonly bint initialized
    
    def __init__(
        self,
        str expression not None,
        int period = 0,
        PriceType price_type = PriceType.LAST,
        str name = None,
    ):
        """Initialize the FactorExpIndicator."""
        Condition.not_none(expression, "expression")
        Condition.not_empty(expression.strip(), "expression")
        
        if RustFactorExpIndicator is None:
            raise RuntimeError(
                "FactorExp Rust module not available. "
                "Please ensure the crate is compiled with 'make build' or 'make install'."
            )
        
        # Create Rust indicator
        try:
            # Convert Cython PriceType to string for PyO3 compatibility
            price_type_str = self._price_type_to_string(price_type)
            
            # Try to parse the expression using Python parser for complex expressions
            try:
                from nautilus_trader.indicators.factorexp.bridge import parse_expression
                compiled_ast = parse_expression(expression)
                if period > 0:
                    self._rust_indicator = RustFactorExpIndicator(
                        expression, period, price_type_str, compiled_ast=compiled_ast
                    )
                else:
                    self._rust_indicator = RustFactorExpIndicator(
                        expression, price_type=price_type_str, compiled_ast=compiled_ast
                    )
            except ImportError:
                # Fallback to direct creation if bridge not available
                if period > 0:
                    self._rust_indicator = RustFactorExpIndicator(expression, period, price_type_str)
                else:
                    self._rust_indicator = RustFactorExpIndicator(expression, price_type=price_type_str)
        except ValueError as e:
            raise ValueError(f"Failed to create FactorExpIndicator: {e}")
        
        # Get actual period from Rust
        self.period = self._rust_indicator.period
        
        # Initialize base class
        super().__init__(params=[expression, self.period])
        
        # Store properties
        self._expression = expression
        self._name = name or self._generate_name(expression)
        
        # Initialize state
        self.value = 0.0
        self.count = 0
        self.initialized = False
    
    cdef str _generate_name(self, str expression):
        """Generate a readable name from the expression."""
        if len(expression) > 40:
            return f"FactorExp({expression[:37]}...)"
        return f"FactorExp({expression})"
    
    cdef str _price_type_to_string(self, PriceType price_type):
        """Convert Cython PriceType enum to string for PyO3 compatibility."""
        if price_type == PriceType.BID:
            return "BID"
        elif price_type == PriceType.ASK:
            return "ASK"
        elif price_type == PriceType.MID:
            return "MID"
        elif price_type == PriceType.LAST:
            return "LAST"
        elif price_type == PriceType.MARK:
            return "MARK"
        else:
            return "LAST"  # Default fallback
    
    @property
    def expression(self) -> str:
        """
        Return the expression string.
        
        Returns
        -------
        str
        
        """
        return self._expression
    
    @property
    def name(self) -> str:
        """
        Return the indicator name.
        
        Returns
        -------
        str
        
        """
        return self._name
    
    cpdef void handle_quote_tick(self, QuoteTick tick):
        """
        Update the indicator with the given quote tick.
        
        Parameters
        ----------
        tick : QuoteTick
            The quote tick to handle.
        
        """
        Condition.not_none(tick, "tick")
        
        self._rust_indicator.handle_quote_tick(tick.to_pyo3())
        self._update_state()
        
    cpdef void handle_trade_tick(self, TradeTick tick):
        """
        Update the indicator with the given trade tick.
        
        Parameters
        ----------
        tick : TradeTick
            The trade tick to handle.
        
        """
        Condition.not_none(tick, "tick")
        
        self._rust_indicator.handle_trade_tick(tick.to_pyo3())
        self._update_state()
    
    cpdef void handle_bar(self, Bar bar):
        """
        Update the indicator with the given bar.
        
        Parameters
        ----------
        bar : Bar
            The bar to handle.
        
        """
        Condition.not_none(bar, "bar")
        
        self._rust_indicator.handle_bar(bar.to_pyo3())
        self._update_state()
    
    cdef void _update_state(self):
        """Update local state from Rust indicator."""
        self.value = self._rust_indicator.value
        self.count = self._rust_indicator.count
        
        # Update initialized state
        if not self.initialized and self._rust_indicator.initialized:
            self.initialized = True
            self._set_initialized(True)
        
        # Update has_inputs
        if self.count > 0 and not self.has_inputs:
            self._set_has_inputs(True)
    
    cpdef void reset(self):
        """Reset the indicator state."""
        self._rust_indicator.reset()
        
        # Reset local state
        self.value = 0.0
        self.count = 0
        self.initialized = False
        
        # Reset base indicator state
        self._set_has_inputs(False)
        self._set_initialized(False)
    
    def __repr__(self) -> str:
        return f"{self._name}(period={self.period})"


# Factory function for creating indicators from expressions
cpdef FactorExpIndicator create_factor_indicator(
    str expression,
    int period = 0,
    PriceType price_type = PriceType.LAST,
    str name = None,
):
    """
    Create a FactorExpIndicator from an expression.
    
    This is a convenience function that creates and returns a new
    FactorExpIndicator instance.
    
    Parameters
    ----------
    expression : str
        The FactorExp expression to evaluate
    period : int, optional
        The lookback period (auto-detected if not provided)
    price_type : PriceType, default=PriceType.LAST
        The price type for quote ticks
    name : str, optional
        Custom name for the indicator
    
    Returns
    -------
    FactorExpIndicator
    
    Examples
    --------
    >>> indicator = create_factor_indicator("TS_Mean($close, 20)")
    >>> momentum = create_factor_indicator(
    ...     "TS_Mean($close, 10) / TS_Mean($close, 30)",
    ...     name="Momentum"
    ... )
    
    """
    return FactorExpIndicator(expression, period, price_type, name)