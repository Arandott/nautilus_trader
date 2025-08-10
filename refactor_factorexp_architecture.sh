#!/bin/bash
# Script to refactor FactorExp to follow Nautilus Trader's standard architecture

echo "=== FactorExp Architecture Refactoring ==="
echo "This script will fix the naming conflicts and align with Nautilus Trader patterns"
echo ""

# Check if we're in the right directory
if [ ! -d "nautilus_trader/indicators/factorexp" ]; then
    echo "Error: Must run from Nautilus Trader root directory"
    exit 1
fi

echo "Step 1: Moving Cython file to correct location..."
if [ -f "nautilus_trader/indicators/factorexp.pyx" ]; then
    mv nautilus_trader/indicators/factorexp.pyx nautilus_trader/indicators/factorexp/indicator.pyx
    echo "✓ Moved factorexp.pyx to factorexp/indicator.pyx"
else
    echo "✗ factorexp.pyx not found in indicators root"
fi

echo ""
echo "Step 2: Backing up old Python implementation..."
if [ -f "nautilus_trader/indicators/factorexp/core/indicator.py" ]; then
    mkdir -p nautilus_trader/indicators/factorexp/_backup
    cp nautilus_trader/indicators/factorexp/core/indicator.py nautilus_trader/indicators/factorexp/_backup/indicator.py.backup
    echo "✓ Backed up old indicator.py"
fi

echo ""
echo "Step 3: Removing conflicting Python implementations..."

# Remove the old Python indicator implementation
if [ -f "nautilus_trader/indicators/factorexp/core/indicator.py" ]; then
    rm nautilus_trader/indicators/factorexp/core/indicator.py
    echo "✓ Removed core/indicator.py"
fi

# Remove other unused Python implementations
files_to_remove=(
    "nautilus_trader/indicators/factorexp/core/engine.py"
    "nautilus_trader/indicators/factorexp/core/bridge.py"
    "nautilus_trader/indicators/factorexp/core/rust_bridge.py"
)

for file in "${files_to_remove[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "✓ Removed $file"
    fi
done

# Remove adapters directory
if [ -d "nautilus_trader/indicators/factorexp/adapters" ]; then
    rm -rf nautilus_trader/indicators/factorexp/adapters
    echo "✓ Removed adapters directory"
fi

# Remove operators directory (using Rust implementation)
if [ -d "nautilus_trader/indicators/factorexp/operators" ]; then
    rm -rf nautilus_trader/indicators/factorexp/operators
    echo "✓ Removed operators directory"
fi

# Remove empty core directory if it exists
if [ -d "nautilus_trader/indicators/factorexp/core" ]; then
    if [ -z "$(ls -A nautilus_trader/indicators/factorexp/core)" ]; then
        rmdir nautilus_trader/indicators/factorexp/core
        echo "✓ Removed empty core directory"
    else
        echo "! core directory not empty, keeping it"
    fi
fi

echo ""
echo "Step 4: Creating clean __init__.py..."
cat > nautilus_trader/indicators/factorexp/__init__.py << 'EOF'
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
EOF

echo "✓ Created clean __init__.py"

echo ""
echo "Step 5: Creating example usage file..."
cat > nautilus_trader/indicators/factorexp/README.md << 'EOF'
# FactorExp Indicator

High-performance expression-based indicators for Nautilus Trader.

## Architecture

The FactorExp indicator follows Nautilus Trader's standard architecture:
- Cython interface (`indicator.pyx`) for Python integration
- Rust backend (via PyO3) for high-performance computation
- Expression parser in Python for flexibility

## Usage

```python
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator

# Create an indicator with an expression
indicator = FactorExpIndicator(
    expression="TS_Mean($close, 20) / TS_Mean($close, 50)",
    name="MomentumRatio"
)

# Use in a strategy
class MyStrategy(Strategy):
    def on_start(self):
        self.register_indicator_for_bars(indicator, self.bar_type)
    
    def on_bar(self, bar: Bar):
        if indicator.initialized:
            signal = indicator.value
            # Trading logic...
```

## Directory Structure

```
factorexp/
├── indicator.pyx          # Main Cython implementation
├── expressions/           # Expression parsing (Python)
│   ├── parser.py
│   ├── validator.py
│   └── ast.py
└── security/             # Security configuration
    └── config.py
```

All computation is performed in Rust for maximum performance.
EOF

echo "✓ Created README.md"

echo ""
echo "=== Refactoring Complete ==="
echo ""
echo "Summary of changes:"
echo "1. Moved factorexp.pyx → factorexp/indicator.pyx"
echo "2. Removed Python implementation (core/indicator.py)"
echo "3. Removed unused directories (adapters/, operators/, core/)"
echo "4. Created clean __init__.py"
echo "5. Created documentation"
echo ""
echo "Next steps:"
echo "1. Update any imports to use: from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator"
echo "2. Run 'make build' to compile the Cython module"
echo "3. Run tests to ensure everything works"
echo ""
echo "Backup location: nautilus_trader/indicators/factorexp/_backup/"