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
FactorExp indicator integration for Nautilus Trader.

High-performance expression-based indicators with Rust backend.
"""

# The main indicator is imported directly from the Cython module:
# from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator

# Expression handling utilities remain in Python for flexibility
from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser, ParseError
from nautilus_trader.indicators.factorexp.expressions.validator import ExpressionValidator
from nautilus_trader.indicators.factorexp.expressions.ast import Expression
from nautilus_trader.indicators.factorexp.security.config import SecurityConfig, SecurityLevel

__all__ = [
    # Expression handling
    "ExpressionParser",
    "ExpressionValidator", 
    "Expression",
    "ParseError",
    
    # Security
    "SecurityConfig",
    "SecurityLevel",
]
