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
Example demonstrating extended fields functionality for Bar objects.

This example shows how to use the extended_bar feature to attach custom
metadata to bars, such as transaction volume (amt), true value settled (tvs),
and order imbalance (oib).

Note: This feature requires the extended_bar feature to be enabled at compile time.
To enable it, modify build.py line 126 to include "extended_bar" in the features string.
"""


from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


def check_extended_bar_feature():
    """Check if the extended_bar feature is enabled."""
    try:
        # Create a test bar
        instrument_id = InstrumentId.from_str("BTC-USDT.BINANCE")
        bar_spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
        bar_type = BarType(instrument_id, bar_spec, AggregationSource.EXTERNAL)

        bar = Bar(
            bar_type,
            Price.from_str("50000.00"),
            Price.from_str("50100.00"),
            Price.from_str("49900.00"),
            Price.from_str("50050.00"),
            Quantity.from_str("100.50"),
            0,
            0,
        )

        if not EXTENDED_BAR_FIELD_SPECS:
            return False

        field = EXTENDED_BAR_FIELD_SPECS[0]
        name = field["name"]

        if not hasattr(bar, name):
            return False

        if field["type"] == "quantity":
            setattr(bar, name, Quantity.from_str("1.0"))
        elif field["type"] == "price":
            setattr(bar, name, Price.from_str("1.0"))
        elif field["type"] == "u64":
            setattr(bar, name, 1)
        elif field["type"] == "bool":
            setattr(bar, name, True)

        return getattr(bar, name) is not None

    except Exception:
        return False


def create_bar_with_extended_fields():
    """Create a bar with extended fields for market microstructure analysis."""
    # Create instrument and bar type
    instrument_id = InstrumentId.from_str("BTC-USDT.BINANCE")
    bar_spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
    bar_type = BarType(instrument_id, bar_spec, AggregationSource.EXTERNAL)

    # Create a bar with standard OHLCV data
    bar = Bar(
        bar_type,
        Price.from_str("50000.00"),  # Open
        Price.from_str("50100.00"),  # High
        Price.from_str("49900.00"),  # Low
        Price.from_str("50050.00"),  # Close
        Quantity.from_str("100.50"),  # Volume
        0,  # ts_event
        0,  # ts_init
    )

    print("Created bar with standard fields:")
    print(f"  Open: {bar.open}")
    print(f"  High: {bar.high}")
    print(f"  Low: {bar.low}")
    print(f"  Close: {bar.close}")
    print(f"  Volume: {bar.volume}")
    print()

    # Add extended fields for advanced analysis when available
    if hasattr(bar, "amt"):
        amt_value = 100.50 * 50025.00  # volume * average price
        bar.amt = Quantity.from_str(f"{amt_value:.2f}")

    if hasattr(bar, "tvs"):
        tvs_value = 100.50 * 50000.00  # volume * execution price
        bar.tvs = Quantity.from_str(f"{tvs_value:.2f}")

    if hasattr(bar, "oib"):
        oib_value = 0.65  # 65% buy volume
        bar.oib = Quantity.from_str(f"{oib_value:.3f}")

    print("Added extended fields:")
    if hasattr(bar, "amt"):
        print(f"  amt (transaction amount): {bar.amt}")
    if hasattr(bar, "tvs"):
        print(f"  tvs (true value settled): {bar.tvs}")
    if hasattr(bar, "oib"):
        print(f"  oib (order imbalance): {bar.oib}")
    print(f"  Has extended fields: {bool(EXTENDED_BAR_FIELD_SPECS)}")
    print()

    return bar


def demonstrate_field_operations(bar):
    """Demonstrate various operations on extended fields."""
    print("Field Operations:")
    print("-" * 40)

    if hasattr(bar, "amt"):
        print(f"Transaction amount exists: {bar.amt}")
    else:
        print("No `amt` field available on this build.")

    # Update an existing field
    print("\nUpdating order imbalance...")
    if hasattr(bar, "oib"):
        new_oib = 0.72  # Update to 72% buy volume
        bar.oib = Quantity.from_str(f"{new_oib:.3f}")
        print(f"Updated OIB: {bar.oib}")
    else:
        print("`oib` field not configured; skipping update.")

    # Try to add a 4th field (will fail as max is 3)
    print("\nTrying to add 4th field...")
    print("Direct attribute access is now preferred; dynamic fields are not supported.")

    # Clear all extended fields
    print("\nClearing all extended fields...")
    if hasattr(bar, "reset_extended_fields"):
        bar.reset_extended_fields()
    elif hasattr(bar, "amt"):
        bar.amt = Quantity.from_str("0")
    print(f"Has extended fields after clear: {bool(EXTENDED_BAR_FIELD_SPECS)}")
    if hasattr(bar, "amt"):
        print(f"amt after clear: {bar.amt}")

    # Add new fields after clearing
    print("\nAdding new fields after clear...")
    if hasattr(bar, "bid_vol"):
        bar.bid_vol = Quantity.from_str("45.25")
        print(f"bid_vol: {bar.bid_vol}")
    if hasattr(bar, "ask_vol"):
        bar.ask_vol = Quantity.from_str("55.25")
        print(f"ask_vol: {bar.ask_vol}")


def use_extended_fields_in_strategy(bars):
    """Example of using extended fields for trading signals."""
    print("\nStrategy Signal Generation:")
    print("-" * 40)

    signals = []
    for i, bar in enumerate(bars):
        oib = getattr(bar, "oib", None)
        amt = getattr(bar, "amt", None)

        if oib is not None and amt is not None:
            # Generate signal based on order imbalance and transaction amount
            if oib > 0.7 and amt > 1_000_000:
                signals.append(("BUY", i, f"Strong buy pressure (OIB: {oib:.2%})"))
            elif oib < 0.3 and amt > 1_000_000:
                signals.append(("SELL", i, f"Strong sell pressure (OIB: {oib:.2%})"))

    for signal_type, bar_idx, reason in signals:
        print(f"Bar {bar_idx}: {signal_type} - {reason}")


def main():
    """Run the extended fields example."""
    print("=" * 60)
    print("Extended Bar Fields Example")
    print("=" * 60)
    print()

    # Check if feature is enabled
    if not check_extended_bar_feature():
        print("WARNING: extended_bar feature is not enabled!")
        print("To enable it:")
        print("1. Edit build.py line 126")
        print("2. Add 'extended_bar' to the features string")
        print("3. Run: make clean && make build-debug")
        print()
        print("Continuing with demo (operations will return default values)...")
        print()

    # Create and demonstrate extended fields
    bar = create_bar_with_extended_fields()
    demonstrate_field_operations(bar)

    # Create multiple bars for strategy example
    print("\n" + "=" * 60)
    print("Creating multiple bars for strategy example...")
    print("=" * 60)

    bars = []
    oib_values = [0.45, 0.55, 0.75, 0.30, 0.65]  # Different order imbalances
    amt_values = [500_000, 750_000, 1_200_000, 1_100_000, 900_000]

    for i, (oib, amt) in enumerate(zip(oib_values, amt_values)):
        instrument_id = InstrumentId.from_str("BTC-USDT.BINANCE")
        bar_spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
        bar_type = BarType(instrument_id, bar_spec, AggregationSource.EXTERNAL)

        bar = Bar(
            bar_type,
            Price.from_str(f"{50000 + i * 10}.00"),
            Price.from_str(f"{50100 + i * 10}.00"),
            Price.from_str(f"{49900 + i * 10}.00"),
            Price.from_str(f"{50050 + i * 10}.00"),
            Quantity.from_str("100.00"),
            i * 60_000_000_000,  # 1 minute intervals
            i * 60_000_000_000,
        )

        if hasattr(bar, "oib"):
            bar.oib = Quantity.from_str(f"{oib:.3f}")
        if hasattr(bar, "amt"):
            bar.amt = Quantity.from_str(f"{amt:.2f}")
        bars.append(bar)

    # Use extended fields in strategy
    use_extended_fields_in_strategy(bars)

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
