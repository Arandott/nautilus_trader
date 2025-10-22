#!/usr/bin/env python3
"""
Real-time amt field verification for live trading.

Tests bar.amt accumulation from live Binance Futures data stream.
Follows official TradingNode pattern for proper lifecycle management.

IMPORTANT: This test requires:
1. Set NT_ENABLE_LIVE_TESTS=1 environment variable
2. Network access to Binance mainnet
3. No API keys needed (public data only)

Run:
    NT_ENABLE_LIVE_TESTS=1 pytest factorexp_live_trading/tests/test_live_amt_field.py -v -s

Architecture:
- Uses TradingNode pattern (NOT manual component assembly)
- Proper lifecycle: kernel.start_async() → subscribe → collect → kernel.stop_async()
- InstrumentProviderConfig with load_ids for targeted loading
- Cache polling instead of hardcoded sleep
- pytest-asyncio manages event loop (do NOT call node.dispose() in tests)
"""

import asyncio
import os
from decimal import Decimal

import pytest

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveDataEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.data.aggregation import TickBarAggregator
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId


# Skip if extended_bar feature is not enabled
pytestmark_extended = pytest.mark.skipif(
    not hasattr(Bar, "amt"),
    reason="extended_bar feature is not enabled in this build",
)

# Skip if NT_ENABLE_LIVE_TESTS is not set (default behavior for CI)
pytestmark_live = pytest.mark.skipif(
    not os.getenv("NT_ENABLE_LIVE_TESTS"),
    reason="NT_ENABLE_LIVE_TESTS environment variable not set. Set to '1' to enable live tests.",
)

pytestmark = [pytestmark_extended, pytestmark_live]


@pytest.mark.asyncio
@pytest.mark.timeout(180)  # 3-minute timeout
async def test_live_amt_accumulation_btcusdt():
    """
    Test that live bars accumulate amt correctly from Binance Futures MAINNET.

    Uses official TradingNode pattern for proper lifecycle management.

    Environment variables:
    - NT_ENABLE_LIVE_TESTS=1 (required to run)

    Duration: ~60-120 seconds to collect 1-2 bars
    """
    NETWORK = "MAINNET (Binance Futures)"
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")

    print()
    print("=" * 80)
    print("Real-Time Amt Field Verification Test")
    print("=" * 80)
    print(f"Network: {NETWORK}")
    print(f"Instrument: {instrument_id}")
    print(f"Extended Bar: {'ENABLED' if hasattr(Bar, 'amt') else 'DISABLED'}")
    print("=" * 80)
    print()

    # Configure TradingNode using official pattern
    config = TradingNodeConfig(
        trader_id=TraderId("TESTER-001"),
        logging=LoggingConfig(
            log_level="INFO",  # Reduce noise
            use_pyo3=True,
        ),
        data_engine=LiveDataEngineConfig(
            debug=False,  # Reduce log verbosity
        ),
        data_clients={
            "BINANCE": BinanceDataClientConfig(
                api_key=None,  # Not needed for public data
                api_secret=None,
                account_type=BinanceAccountType.USDT_FUTURE,
                testnet=False,  # ALWAYS use mainnet
                us=False,
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,
                    load_ids=frozenset({instrument_id}),  # Load only target instrument
                ),
            ),
        },
        timeout_connection=30.0,
        timeout_disconnection=10.0,
    )

    # Create node
    node = TradingNode(config=config)

    # Register data client factory (REQUIRED before build)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)

    # Build node (initializes all components)
    node.build()

    print("✅ TradingNode built")
    print()

    # Track data using Decimal for precision
    trades = []
    bars = []
    expected_amt_decimal = Decimal("0")

    def on_trade(tick):
        """Track trades for manual amt calculation using Decimal."""
        nonlocal expected_amt_decimal

        price_decimal = tick.price.as_decimal()
        size_decimal = tick.size.as_decimal()
        trade_amt = price_decimal * size_decimal

        trades.append((tick.ts_event, price_decimal, size_decimal))
        expected_amt_decimal += trade_amt

        if len(trades) % 10 == 0:
            print(f"  📊 Trades: {len(trades)}, Expected Amt: ${float(expected_amt_decimal):,.2f}")

    def on_bar(bar: Bar):
        """Verify bar amt field using Decimal arithmetic."""
        nonlocal expected_amt_decimal

        actual_amt_decimal = bar.amt.as_decimal()

        bars.append({
            'bar': bar,
            'actual_amt': actual_amt_decimal,
            'expected_amt': expected_amt_decimal,
            'trade_count': len(trades),
        })

        diff = abs(actual_amt_decimal - expected_amt_decimal)
        diff_pct = (diff / expected_amt_decimal) * Decimal("100") if expected_amt_decimal > 0 else Decimal("0")

        print()
        print(f"🎯 Bar #{len(bars)} Completed:")
        print(f"   OHLCV: {bar.open} / {bar.high} / {bar.low} / {bar.close} / {bar.volume}")
        print(f"   Trades: {len(trades)}")
        print(f"   Actual amt:   ${float(actual_amt_decimal):,.2f}")
        print(f"   Expected amt: ${float(expected_amt_decimal):,.2f}")
        print(f"   Difference:   ${float(diff):,.2f} ({float(diff_pct):.6f}%)")

        threshold = Decimal("0.01")
        assert diff_pct < threshold, (
            f"amt field error {float(diff_pct):.6f}% exceeds {float(threshold)}% threshold"
        )

        print(f"   ✅ PASS: amt field accurate (error < {float(threshold)}%)")
        print()

        trades.clear()
        expected_amt_decimal = Decimal("0")

    # Bar configuration
    bar_spec = BarSpecification(
        step=100,
        aggregation=BarAggregation.TICK,
        price_type=PriceType.LAST,
    )
    bar_type = BarType(
        instrument_id=instrument_id,
        bar_spec=bar_spec,
        aggregation_source=AggregationSource.EXTERNAL,
    )

    try:
        # Start node kernel (async startup)
        await node.kernel.start_async()
        print("✅ TradingNode kernel started")
        print()

        # Poll cache until instrument is loaded (proper waiting pattern)
        print("Waiting for instrument to load...")
        max_retries = 10
        retry_delay = 1.0
        instrument = None

        for attempt in range(max_retries):
            instrument = node.cache.instrument(instrument_id)
            if instrument is not None:
                break
            print(f"  Attempt {attempt + 1}/{max_retries}: Instrument not yet cached, retrying...")
            await asyncio.sleep(retry_delay)

        assert instrument is not None, f"Failed to load {instrument_id} after {max_retries} attempts"

        print(f"✅ Instrument loaded: {instrument.id}")
        print()

        print(f"Bar Configuration:")
        print(f"  - Type: {bar_type}")
        print(f"  - Aggregation: {bar_spec.step} ticks")
        print()

        # Create aggregator
        aggregator = TickBarAggregator(
            instrument=instrument,
            bar_type=bar_type,
            handler=on_bar,
        )

        # Define handlers as variables for cleanup
        def trade_handler(msg):
            if hasattr(msg, 'price'):
                on_trade(msg)

        def aggregator_handler(msg):
            if hasattr(msg, 'price'):
                aggregator.handle_trade_tick(msg)

        # Subscribe to message bus
        topic = f"data.trades.{instrument_id.venue}.{instrument_id.symbol}"
        node.msgbus.subscribe(topic=topic, handler=trade_handler)
        node.msgbus.subscribe(topic=topic, handler=aggregator_handler)

        # Subscribe to trade ticks via data engine
        node.data_engine.subscribe_trade_ticks(instrument_id)

        print("✅ Subscribed to live data stream")
        print()
        print("Collecting data for 120 seconds...")
        print("=" * 80)
        print()

        # Collect data
        await asyncio.sleep(120)

        print()
        print("=" * 80)
        print("Stopping data collection...")
        print()

        # Unsubscribe
        try:
            node.data_engine.unsubscribe_trade_ticks(instrument_id)
        except Exception as e:
            print(f"⚠️  Warning: Failed to unsubscribe: {e}")

        try:
            node.msgbus.unsubscribe(topic, trade_handler)
            node.msgbus.unsubscribe(topic, aggregator_handler)
        except Exception as e:
            print(f"⚠️  Warning: Failed to unsubscribe handlers: {e}")

        trades.clear()

        print("✅ Cleanup complete")
        print()

    finally:
        # Always stop node kernel (let pytest manage the event loop)
        await node.kernel.stop_async()
        print("✅ TradingNode kernel stopped")
        print()

    # Verify results
    assert len(bars) >= 1, f"Expected at least 1 bar, got {len(bars)}"

    print("=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print(f"  Network: {NETWORK}")
    print(f"  Bars collected: {len(bars)}")
    print(f"  All amt fields accurate within 0.01%")
    print()

    for i, bar_data in enumerate(bars, 1):
        actual = bar_data['actual_amt']
        expected = bar_data['expected_amt']
        diff_pct = abs(actual - expected) / expected * Decimal("100") if expected > 0 else Decimal("0")

        print(f"  Bar #{i}:")
        print(f"    Actual:   ${float(actual):,.2f}")
        print(f"    Expected: ${float(expected):,.2f}")
        print(f"    Error:    {float(diff_pct):.6f}%")
        print()

    print("=" * 80)
    print("✅ TEST PASSED")
    print("=" * 80)
    print()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
