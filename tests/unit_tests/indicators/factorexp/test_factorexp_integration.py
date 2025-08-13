#!/usr/bin/env python3
"""
Test script for FactorExp Python-Rust integration.

This script tests the complete integration of:
1. Python expression parsing
2. Python-to-Rust AST conversion
3. Rust execution engine
"""

import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_bridge():
    """Test the Python-Rust bridge."""
    print("=" * 60)
    print("Testing Python-Rust Bridge")
    print("=" * 60)
    
    from nautilus_trader.indicators.factorexp.bridge import ExpressionBridge
    
    bridge = ExpressionBridge()
    
    # Test cases
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
            result = bridge.parse_and_convert(expr)
            print(f"✅ Parsed successfully")
            print(f"   Result type: {result.get('type')}")
            if result.get('type') == 'Operator':
                print(f"   Operator: {result.get('name')}")
                print(f"   Args count: {len(result.get('args', []))}")
                print(f"   Params: {result.get('params', {})}")
        except Exception as e:
            print(f"❌ Failed: {e}")


def test_rust_compilation():
    """Test the Rust compilation function."""
    print("\n" + "=" * 60)
    print("Testing Rust Compilation")
    print("=" * 60)
    
    try:
        from nautilus_trader.core.nautilus_pyo3.factorexp import compile_expression_from_python
        print("✅ Rust module imported successfully")
    except ImportError as e:
        print(f"❌ Rust module not available: {e}")
        print("   Please run 'make build' to compile the Rust code")
        return
    
    from nautilus_trader.indicators.factorexp.bridge import parse_expression
    
    # Test compilation
    test_expr = "TS_Mean($close, 20)"
    print(f"\nCompiling: {test_expr}")
    
    try:
        ast_dict = parse_expression(test_expr)
        print(f"✅ Parsed to AST: {ast_dict}")
        
        compiled = compile_expression_from_python(ast_dict)
        print(f"✅ Compiled successfully")
        print(f"   Compiled result: {compiled}")
    except Exception as e:
        print(f"❌ Compilation failed: {e}")


def test_indicator_creation():
    """Test creating an indicator with the full stack."""
    print("\n" + "=" * 60)
    print("Testing Indicator Creation")
    print("=" * 60)
    
    try:
        from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
        from nautilus_trader.model.data import Bar, BarType, BarSpecification
        from nautilus_trader.model.objects import Price, Quantity
        from nautilus_trader.model.enums import BarAggregation, AggregationSource, PriceType
        from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
        from nautilus_trader.core.uuid import UUID4
        import time
        
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
        indicator.handle_bar(bar)
        print(f"✅ Value: {indicator.value}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
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
    print("\nTesting complex expression: TS_Mean($close, 5) / TS_Mean($close, 10)")
    try:
        indicator = FactorExpIndicator("TS_Mean($close, 5) / TS_Mean($close, 10)")
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
    
    # Test 1: Bridge
    test_bridge()
    
    # Test 2: Rust compilation
    test_rust_compilation()
    
    # Test 3: Full indicator creation
    test_indicator_creation()
    
    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()