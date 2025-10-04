#!/usr/bin/env python3
"""
Test script for FactorExp Python-Rust integration.

This script tests the complete integration of:
1. Direct string-to-Rust expression parsing
2. Rust compilation and execution
3. Full indicator functionality with market data
"""

import sys
import traceback
from pathlib import Path


# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_direct_rust_parsing():
    """Test the direct Python-to-Rust string parsing."""
    print("=" * 60)
    print("Testing Direct String Parsing in Rust")
    print("=" * 60)

    try:
        from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
        print("✅ FactorExpIndicator imported successfully")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return

    # Test cases - all parsing happens directly in Rust now
    test_cases = [
        "$close",
        "TS_Mean($close, 20)",
        "TS_Mean($close, 20) / TS_Mean($close, 50)",
        "($high + $low) / 2",
        "(TS_Mean($close, 20) - TS_Mean($close, 50)) / TS_Std($close, 20)",
    ]

    for expr in test_cases:
        print(f"\nExpression: {expr}")
        try:
            # New architecture: string goes directly to Rust
            indicator = FactorExpIndicator(expr)
            print("✅ Parsed and compiled successfully in Rust")
            print(f"   Period: {indicator.period}")
            print(f"   Expression: {indicator.expression}")
        except Exception as e:
            print(f"❌ Failed: {e}")


def test_rust_module_availability():
    """Test that the Rust module is compiled and accessible."""
    print("\n" + "=" * 60)
    print("Testing Rust Module Availability")
    print("=" * 60)

    try:
        # Test that the Rust factorexp module exists
        from nautilus_trader.core.nautilus_pyo3 import factorexp
        print("✅ Rust factorexp module found")

        # Check for FactorExpIndicator in the module
        if hasattr(factorexp, "FactorExpIndicator"):
            print("✅ FactorExpIndicator class available in Rust module")
        else:
            print("⚠️  FactorExpIndicator not found in module")

        # Test creating an indicator directly from Rust module
        test_expr = "TS_Mean($close, 20)"
        print(f"\nTesting Rust indicator creation with: {test_expr}")

        try:
            # Direct Rust instantiation (with new architecture)
            rust_indicator = factorexp.FactorExpIndicator(test_expr)
            print("✅ Created Rust indicator directly")
            print(f"   Period: {rust_indicator.period}")
            print(f"   Expression: {rust_indicator.expression}")
        except Exception as e:
            print(f"❌ Failed to create Rust indicator: {e}")

    except ImportError as e:
        print(f"❌ Rust module not available: {e}")
        print("   Please run 'make build' to compile the Rust code")
        return


def test_indicator_creation():
    """Test creating an indicator with the full stack."""
    print("\n" + "=" * 60)
    print("Testing Indicator Creation")
    print("=" * 60)

    try:
        import time

        from nautilus_trader.core.nautilus_pyo3 import PriceType
        from nautilus_trader.core.uuid import UUID4
        from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
        from nautilus_trader.model.data import Bar
        from nautilus_trader.model.data import BarSpecification
        from nautilus_trader.model.data import BarType
        from nautilus_trader.model.enums import AggregationSource
        from nautilus_trader.model.enums import BarAggregation
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.identifiers import Symbol
        from nautilus_trader.model.identifiers import Venue
        from nautilus_trader.model.objects import Price
        from nautilus_trader.model.objects import Quantity

        print("✅ Imports successful")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return

    # Create test bar
    bar_type = BarType(
        instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
        bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        aggregation_source=AggregationSource.EXTERNAL,
    )

    bar = Bar(
        bar_type=bar_type,
        open=Price.from_str("100.00"),
        high=Price.from_str("101.00"),
        low=Price.from_str("99.00"),
        close=Price.from_str("100.50"),
        volume=Quantity.from_str("1000"),
        ts_event=int(time.time() * 1e9),
        ts_init=int(time.time() * 1e9),
    )

    # Test simple expression
    print("\nTesting simple expression: $close")
    try:
        indicator = FactorExpIndicator("$close")
        print("Pass.")
        indicator.handle_bar(bar)
        print(f"✅ Value: {indicator.value}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        traceback.print_exc()
        # print(f"❌ Failed: {e}")

    # Test rolling operator
    print("\nTesting rolling operator: TS_Mean($close, 5)")
    try:
        indicator = FactorExpIndicator("TS_Mean($close, 5)")
        for i in range(10):
            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(f"{100.0 + i}"),
                high=Price.from_str(f"{101.0 + i}"),
                low=Price.from_str(f"{99.0 + i}"),
                close=Price.from_str(f"{100.0 + i}"),
                volume=Quantity.from_str("1000"),
                ts_event=int(time.time() * 1e9) + i * int(1e9),
                ts_init=int(time.time() * 1e9) + i * int(1e9),
            )
            indicator.handle_bar(bar)
        print(f"✅ Value after 10 bars: {indicator.value}")
        print(f"   Initialized: {indicator.initialized}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # Test complex expression
    print("\nTesting complex expression: TS_Mean($close, 2) / TS_Mean($close, 15)")
    try:
        indicator = FactorExpIndicator("TS_Mean($close, 2) / TS_Mean($close, 15)")
        for i in range(15):
            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(f"{100.0 + i * 0.5}"),
                high=Price.from_str(f"{101.0 + i * 0.5}"),
                low=Price.from_str(f"{99.0 + i * 0.5}"),
                close=Price.from_str(f"{100.0 + i * 0.5}"),
                volume=Quantity.from_str("1000"),
                ts_event=int(time.time() * 1e9) + i * int(1e9),
                ts_init=int(time.time() * 1e9) + i * int(1e9),
            )
            indicator.handle_bar(bar)
        print(f"✅ Value after 15 bars: {indicator.value}")
        print(f"   Initialized: {indicator.initialized}")
    except Exception as e:
        print(f"❌ Failed: {e}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("FactorExp Integration Test Suite")
    print("=" * 60)

    # Test 1: Direct Rust parsing (new architecture)
    test_direct_rust_parsing()

    # Test 2: Rust module availability
    test_rust_module_availability()

    # Test 3: Full indicator creation
    test_indicator_creation()

    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
