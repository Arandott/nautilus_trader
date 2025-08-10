#!/usr/bin/env python3
"""
Simple demonstration of FactorExp integration with Nautilus Trader.

This script shows how to use various FactorExp expressions.
"""

import numpy as np
from datetime import datetime

from nautilus_trader.indicators.factorexp import FactorExpIndicator, SecurityConfig
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.enums import BarAggregation, AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue


def create_test_bar(close: float, volume: float = 1000.0, high_mult: float = 1.01, low_mult: float = 0.99) -> Bar:
    """Create a test bar."""
    bar_type = BarType(
        instrument_id=InstrumentId(Symbol("TEST"), Venue("SIM")),
        bar_spec=BarSpecification(1, BarAggregation.MINUTE),
        aggregation_source=AggregationSource.EXTERNAL,
    )
    
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(str(close)),
        high=Price.from_str(str(close * high_mult)),
        low=Price.from_str(str(close * low_mult)),
        close=Price.from_str(str(close)),
        volume=Quantity.from_str(str(volume)),
        ts_event=0,
        ts_init=0,
    )


def demo_simple_expressions():
    """Demonstrate simple FactorExp expressions."""
    print("=== Simple Expressions Demo ===\n")
    
    # 1. Feature extraction
    indicator = FactorExpIndicator("$close")
    bar = create_test_bar(100.0)
    indicator.handle_bar(bar)
    print(f"Close price: {indicator.value}")
    
    # 2. Arithmetic
    indicator = FactorExpIndicator("$high - $low")
    indicator.handle_bar(bar)
    print(f"Price range: {indicator.value:.4f}")
    
    # 3. Percentage
    indicator = FactorExpIndicator("($high - $low) / $close * 100")
    indicator.handle_bar(bar)
    print(f"Price range %: {indicator.value:.2f}%")
    
    print()


def demo_rolling_operations():
    """Demonstrate rolling window operations."""
    print("=== Rolling Operations Demo ===\n")
    
    # Create indicator for 5-period moving average
    ma_indicator = FactorExpIndicator("TS_Mean($close, 5)", period=5)
    
    # Generate price series
    prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109]
    
    print("Price | 5-Period MA")
    print("-" * 20)
    
    for i, price in enumerate(prices):
        bar = create_test_bar(float(price))
        ma_indicator.handle_bar(bar)
        
        if ma_indicator.initialized:
            print(f"{price:5} | {ma_indicator.value:8.2f}")
        else:
            print(f"{price:5} | Not ready")
    
    print()


def demo_volatility_indicators():
    """Demonstrate volatility-based indicators."""
    print("=== Volatility Indicators Demo ===\n")
    
    # Sharpe-like ratio
    sharpe_indicator = FactorExpIndicator(
        "TS_Mean($close, 20) / TS_Std($close, 20)",
        period=20,
        name="SharpeRatio"
    )
    
    # Generate volatile price series
    np.random.seed(42)
    base_price = 100
    prices = []
    
    for i in range(30):
        # Random walk with drift
        change = np.random.normal(0.1, 2.0)
        base_price += change
        prices.append(max(base_price, 50))  # Floor at 50
    
    print("Processing 30 bars...")
    for i, price in enumerate(prices):
        bar = create_test_bar(price)
        sharpe_indicator.handle_bar(bar)
    
    if sharpe_indicator.initialized:
        print(f"Sharpe-like Ratio: {sharpe_indicator.value:.4f}")
    
    # Volatility indicator
    vol_indicator = FactorExpIndicator("TS_Std($close, 20)", period=20)
    
    # Re-process the same data
    for price in prices:
        bar = create_test_bar(price)
        vol_indicator.handle_bar(bar)
    
    if vol_indicator.initialized:
        print(f"20-Period Volatility: {vol_indicator.value:.4f}")
    
    print()


def demo_vwap():
    """Demonstrate Volume-Weighted Average Price."""
    print("=== VWAP Demo ===\n")
    
    vwap_indicator = FactorExpIndicator(
        "TS_Sum($close * $volume, 10) / TS_Sum($volume, 10)",
        period=10,
        name="VWAP_10"
    )
    
    # Price and volume data
    data = [
        (100.0, 1000),
        (101.0, 1500),
        (102.0, 2000),
        (101.5, 1200),
        (103.0, 2500),
        (104.0, 1800),
        (103.5, 1600),
        (105.0, 3000),
        (104.5, 2200),
        (106.0, 2800),
    ]
    
    print("Price | Volume | VWAP")
    print("-" * 30)
    
    for price, volume in data:
        bar = create_test_bar(price, float(volume))
        vwap_indicator.handle_bar(bar)
        
        if vwap_indicator.initialized:
            print(f"{price:5.1f} | {volume:6} | {vwap_indicator.value:6.2f}")
        else:
            print(f"{price:5.1f} | {volume:6} | Not ready")
    
    print()


def demo_complex_expressions():
    """Demonstrate complex factor expressions."""
    print("=== Complex Expressions Demo ===\n")
    
    # Momentum-based factor
    momentum_factor = FactorExpIndicator(
        "($close - TS_Ref($close, 5)) / TS_Ref($close, 5) * 100",
        period=5,
        name="Momentum_5"
    )
    
    # Price efficiency ratio
    efficiency_factor = FactorExpIndicator(
        "Abs($close - TS_Ref($close, 10)) / TS_Sum(Abs($close - TS_Ref($close, 1)), 10)",
        period=10,
        name="EfficiencyRatio"
    )
    
    # Generate trending price data
    prices = []
    base = 100
    for i in range(20):
        if i < 10:
            base += 1  # Uptrend
        else:
            base -= 0.5  # Downtrend
        prices.append(base + np.random.normal(0, 0.5))
    
    print("Processing trend data...")
    for price in prices:
        bar = create_test_bar(price)
        momentum_factor.handle_bar(bar)
        efficiency_factor.handle_bar(bar)
    
    if momentum_factor.initialized:
        print(f"5-Period Momentum: {momentum_factor.value:.2f}%")
    
    if efficiency_factor.initialized:
        print(f"Efficiency Ratio: {efficiency_factor.value:.4f}")
    
    print()


def demo_security_levels():
    """Demonstrate different security configurations."""
    print("=== Security Levels Demo ===\n")
    
    # Standard security (default)
    try:
        standard_indicator = FactorExpIndicator("Log($close)")
        print("✓ Standard security allows Log operator")
    except ValueError as e:
        print(f"✗ Standard security error: {e}")
    
    # Paranoid security
    try:
        paranoid_config = SecurityConfig.paranoid()
        paranoid_indicator = FactorExpIndicator(
            "Pow($close, 2)",
            security_config=paranoid_config
        )
        print("✓ Paranoid security allows Pow operator")
    except ValueError as e:
        print(f"✗ Paranoid security blocks Pow: {str(e)[:50]}...")
    
    # Trusted security
    trusted_config = SecurityConfig.trusted()
    trusted_indicator = FactorExpIndicator(
        "Sin($close / 100) * Cos($close / 100)",
        security_config=trusted_config
    )
    bar = create_test_bar(314.159)
    trusted_indicator.handle_bar(bar)
    print(f"✓ Trusted security allows trig functions: {trusted_indicator.value:.4f}")
    
    print()


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 50)
    print("FactorExp-Nautilus Trader Integration Demo")
    print("=" * 50 + "\n")
    
    demo_simple_expressions()
    demo_rolling_operations()
    demo_volatility_indicators()
    demo_vwap()
    demo_complex_expressions()
    demo_security_levels()
    
    print("=" * 50)
    print("Demo completed successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()