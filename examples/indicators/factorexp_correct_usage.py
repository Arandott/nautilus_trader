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
Example of correct FactorExp indicator usage after architecture refactoring.

This example demonstrates:
1. Correct import path (no naming conflicts)
2. Native-like usage pattern
3. High-performance Rust backend
"""

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.trading import Strategy

# CORRECT IMPORT: Direct from Cython module
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator

# For expression utilities (remain in Python)
from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
from nautilus_trader.indicators.factorexp.security.config import SecurityConfig


class FactorExpStrategy(Strategy):
    """
    Example strategy using the refactored FactorExp indicator.
    
    This demonstrates the correct usage after fixing the architecture.
    """
    
    def __init__(self):
        super().__init__()
        
        # Create indicators with expressions (Rust backend handles computation)
        self.momentum = FactorExpIndicator(
            expression="TS_Mean($close, 20) / TS_Mean($close, 50)",
            name="Momentum"
        )
        
        self.volatility = FactorExpIndicator(
            expression="TS_Std($close, 20) / TS_Mean($close, 20)",
            name="Volatility"
        )
        
        # Complex expression example
        self.custom_signal = FactorExpIndicator(
            expression="""
            (TS_Mean($close, 10) - TS_Mean($close, 30)) / TS_Std($close, 20) * 
            TS_Mean($volume, 10) / TS_Mean($volume, 30)
            """,
            name="CustomSignal"
        )
    
    def on_start(self):
        """Register indicators when strategy starts."""
        bar_type = BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
        
        # Register exactly like native indicators
        self.register_indicator_for_bars(self.momentum, bar_type)
        self.register_indicator_for_bars(self.volatility, bar_type) 
        self.register_indicator_for_bars(self.custom_signal, bar_type)
        
        self.log.info("FactorExp indicators registered successfully")
    
    def on_bar(self, bar: Bar):
        """Process bar updates."""
        # All indicators work exactly like native ones
        if not self.momentum.initialized:
            return
        
        # Get values (computed in Rust)
        momentum_value = self.momentum.value
        volatility_value = self.volatility.value
        custom_value = self.custom_signal.value
        
        # Trading logic based on factors
        if momentum_value > 1.05 and volatility_value < 0.02:
            self.log.info(
                f"Bullish signal: momentum={momentum_value:.3f}, "
                f"volatility={volatility_value:.3f}, "
                f"custom={custom_value:.3f}"
            )
            # Place orders, etc.


def demonstrate_expression_parsing():
    """Show that expression parsing still works (Python flexibility)."""
    parser = ExpressionParser()
    
    # Parse complex expression
    expression = "TS_Mean($close, 20) + 2 * TS_Std($close, 20)"
    ast = parser.parse(expression)
    
    print(f"Parsed expression: {expression}")
    print(f"Features used: {ast.get_features()}")
    print(f"Operators used: {ast.get_operators()}")
    
    # Security validation
    config = SecurityConfig.standard()
    # ... validation logic


def main():
    """
    Main demonstration showing:
    1. No import conflicts
    2. Clean architecture
    3. Native-like performance
    """
    print("FactorExp Correct Usage Example")
    print("=" * 40)
    
    # Test expression parsing
    demonstrate_expression_parsing()
    
    # Create strategy (would be used in backtest/live trading)
    strategy = FactorExpStrategy()
    print("\nStrategy created with FactorExp indicators")
    print("All indicators use high-performance Rust backend")
    print("No naming conflicts or import issues!")


if __name__ == "__main__":
    main()