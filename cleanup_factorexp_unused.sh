#!/bin/bash
# Script to remove unused FactorExp files after migration to native implementation

echo "Removing unused FactorExp adapter and bridge files..."

# Remove adapter directory
if [ -d "nautilus_trader/indicators/factorexp/adapters" ]; then
    echo "Removing adapters directory..."
    rm -rf nautilus_trader/indicators/factorexp/adapters/
    echo "✓ Removed adapters directory"
else
    echo "✗ Adapters directory not found"
fi

# Remove bridge.py
if [ -f "nautilus_trader/indicators/factorexp/core/bridge.py" ]; then
    echo "Removing bridge.py..."
    rm nautilus_trader/indicators/factorexp/core/bridge.py
    echo "✓ Removed bridge.py"
else
    echo "✗ bridge.py not found"
fi

# Optional: Remove old Python implementation after confirming Rust works
# Uncomment the following lines after testing the Rust implementation
# if [ -f "nautilus_trader/indicators/factorexp/core/indicator.py" ]; then
#     echo "Backing up old indicator.py..."
#     mv nautilus_trader/indicators/factorexp/core/indicator.py nautilus_trader/indicators/factorexp/core/indicator.py.backup
#     echo "✓ Backed up old indicator.py"
# fi

echo "Cleanup complete!"
echo ""
echo "Next steps:"
echo "1. Run 'make build' to compile the Rust implementation"
echo "2. Run tests to ensure everything works"
echo "3. If all tests pass, you can remove the backup files"