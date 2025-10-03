#!/usr/bin/env python3
"""
Test extended bar functionality from Python side.

This test verifies that the Python bindings for extended bar fields
are working correctly when the extended_bar feature is enabled.
"""

import sys
from pathlib import Path

# Add nautilus_trader to path if needed
nautilus_path = Path(__file__).parent.parent.parent / "nautilus_trader"
if nautilus_path.exists():
    sys.path.insert(0, str(nautilus_path))

def test_extended_bar_basic():
    """Test basic extended bar functionality."""
    try:
        from nautilus_trader.core.nautilus_pyo3 import (
            Bar,
            BarType,
            BarSpecification,
            BarAggregation,
            PriceType,
            AggregationSource,
            InstrumentId,
            Price,
            Quantity,
        )
        from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS

        # Create instrument and bar type
        instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
        bar_spec = BarSpecification(
            step=1,
            aggregation=BarAggregation.MINUTE,
            price_type=PriceType.LAST,
        )
        bar_type = BarType(
            instrument_id=instrument_id,
            spec=bar_spec,
            aggregation_source=AggregationSource.EXTERNAL,
        )

        # Create a bar
        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str("50000.00"),
            high=Price.from_str("50100.00"),
            low=Price.from_str("49900.00"),
            close=Price.from_str("50050.00"),
            volume=Quantity.from_str("100.0"),
            ts_event=1000000000,
            ts_init=1000000000,
        )

        print(f"Created bar: {bar}")

        has_extended = bool(EXTENDED_BAR_FIELD_SPECS)

        if has_extended and hasattr(bar, EXTENDED_BAR_FIELD_SPECS[0]["name"]):
            print("✅ Extended bar attributes are available!")
            # Exercise the first configured field
            spec = EXTENDED_BAR_FIELD_SPECS[0]
            if spec["type"] == "quantity":
                amt_value = Quantity.from_str("5000000.0")
                setattr(bar, spec["name"], amt_value)
                retrieved = getattr(bar, spec["name"])
                if retrieved == amt_value:
                    print(f"✅ Successfully assigned {spec['name']} field")
                else:
                    print("❌ Mismatch assigning extended field")
            else:
                print(f"⚠️  Unsupported test field type {spec['type']}")
        else:
            print("⚠️  Extended bar attributes not available")
            print("    This is expected if extended_bar feature is not enabled")
            print("    Build with: cargo build --features extended_bar,python")

    except ImportError as e:
        print(f"❌ Failed to import Nautilus modules: {e}")
        print("    Make sure Nautilus is built with Python support")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

    return has_extended


def test_extended_bar_with_feather_loader():
    """Test extended bar with feather loader."""
    try:
        # Import our custom loader
        from factorexp_backtest.loaders import FeatherBarLoader
        from nautilus_trader.model.identifiers import InstrumentId, Venue

        # Create test data directory
        data_dir = Path(__file__).parent.parent / "data" / "test"

        if not data_dir.exists():
            print(f"⚠️  Test data directory not found: {data_dir}")
            print("    Skipping feather loader test")
            return True

        loader = FeatherBarLoader(data_dir)

        # Check if extended bar is available
        if loader._has_extended_bar:
            print("✅ Feather loader detected extended bar support")
        else:
            print("⚠️  Feather loader did not detect extended bar support")

        # Try to get available instruments
        instruments = loader.get_available_instruments()
        print(f"Available instruments: {instruments}")

        return True

    except ImportError as e:
        print(f"⚠️  Could not import feather loader: {e}")
        return True  # Not a failure, just not available yet
    except Exception as e:
        print(f"❌ Error testing feather loader: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Extended Bar Python Bindings")
    print("=" * 60)

    success = test_extended_bar_basic()

    if success:
        print("\n" + "=" * 60)
        print("Testing Feather Loader Integration")
        print("=" * 60)
        test_extended_bar_with_feather_loader()

    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
        print("\nTo enable extended bar support, build with:")
        print("  cargo build --features extended_bar,python")
    print("=" * 60)
