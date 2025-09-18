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

# All expression parsing/compilation is handled internally by Rust
# No parsing interfaces are exposed at the Python level

__all__ = [
    # Empty for now - indicator is imported from .indicator module
]
