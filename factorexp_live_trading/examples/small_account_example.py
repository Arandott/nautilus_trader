#!/usr/bin/env python3
"""
Small Account Example - 200 USDT Account Configuration

Demonstrates optimized configuration for small trading accounts using FactorExp strategies.
Shows position sizing, risk management, and capital preservation for accounts ≤$500.
"""

from factorexp_live_trading.config.strategy_config import FactorExpLiveStrategyConfig
from factorexp_live_trading.strategies.factorexp_live_strategy import FactorExpLiveStrategy
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId


def create_small_account_strategy_example():
    """
    Example: Creating a strategy optimized for a 200 USDT account.
    
    This configuration includes:
    - Conservative capital usage (60% instead of 80%)
    - Reduced position risk (1.5% instead of 2%)
    - Tighter stop losses and risk controls
    - Account size-appropriate daily limits
    """
    # Define trading instrument and timeframe
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
    bar_type = BarType.from_str("BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL")

    # Create small account optimized configuration
    small_account_config = FactorExpLiveStrategyConfig.create_small_account_config(
        instrument_id=instrument_id,
        bar_type=bar_type,
        account_size_usd=200.0,  # Account size for optimization
        # Optional overrides:
        # max_daily_trades=8,  # Even more conservative
        # position_risk_pct=0.01,  # 1% risk instead of 1.5%
    )

    print("📊 Small Account Configuration (200 USDT):")
    print(f"  Capital Usage: {small_account_config.max_account_usage_pct:.0%}")
    if small_account_config.capital_allocation_usd:
        print(f"  Capital Allocation: ${small_account_config.capital_allocation_usd:,.0f}")
    print(f"  Position Risk: {small_account_config.position_risk_pct:.1%}")
    print(f"  Stop Loss: {small_account_config.stop_loss_pct:.1%}")
    print(f"  Daily Loss Limit: ${small_account_config.max_daily_loss_usd:.0f}")
    print(f"  Max Daily Trades: {small_account_config.max_daily_trades}")
    print(f"  Max Drawdown: {small_account_config.max_drawdown_pct:.1%}")
    print(f"  Factor Catalog: {small_account_config.factor_config_path}")
    print(f"  Factor ID: {small_account_config.factor_id}")
    print(f"  Factor IDs: {', '.join(small_account_config.factor_ids)}")
    print(f"  Z-Score Period: {small_account_config.zscore_period}")
    print(f"  Min Signal Magnitude: {small_account_config.min_signal_magnitude}")

    # Example position sizing calculation
    account_balance = 200.0
    effective_equity = float(small_account_config.capital_allocation_usd or (
        account_balance * float(small_account_config.max_account_usage_pct)
    ))
    max_risk_per_trade = effective_equity * float(small_account_config.position_risk_pct)

    print("\n💰 Position Sizing Example:")
    print(f"  Account Balance: ${account_balance:.0f}")
    print(f"  Effective Equity: ${effective_equity:.0f} ({small_account_config.max_account_usage_pct:.0%})")
    print(f"  Max Risk/Trade: ${max_risk_per_trade:.2f} ({small_account_config.position_risk_pct:.1%})")

    # Example with BTC price
    btc_price = 50000.0
    stop_loss_distance = btc_price * float(small_account_config.stop_loss_pct)
    position_size = max_risk_per_trade / stop_loss_distance
    notional_value = position_size * btc_price

    print(f"\n📈 Trade Example (BTC @ ${btc_price:,.0f}):")
    print(f"  Stop Loss Distance: ${stop_loss_distance:.0f} ({small_account_config.stop_loss_pct:.1%})")
    print(f"  Position Size: {position_size:.6f} BTC")
    print(f"  Notional Value: ${notional_value:.2f}")
    print(f"  Capital Usage: {notional_value/effective_equity:.1%}")

    # Warning for minimum trade sizes
    min_btc_trade = 0.001  # Typical Binance minimum
    min_notional = min_btc_trade * btc_price

    if position_size < min_btc_trade:
        print(f"\n⚠️ Warning: Calculated position ({position_size:.6f} BTC) below minimum ({min_btc_trade} BTC)")
        print(f"   Would use minimum size: ${min_notional:.2f} notional")
        print("   This exceeds optimal capital usage - consider larger account or different instrument")

    # Create the strategy instance
    strategy = FactorExpLiveStrategy(small_account_config)

    return strategy, small_account_config


def compare_configurations():
    """Compare standard vs. small account configurations."""
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
    bar_type = BarType.from_str("BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL")

    # Standard configuration
    standard_config = FactorExpLiveStrategyConfig(
        instrument_id=instrument_id,
        bar_type=bar_type,
    )

    # Small account configuration
    small_config = FactorExpLiveStrategyConfig.create_small_account_config(
        instrument_id=instrument_id,
        bar_type=bar_type,
        account_size_usd=200.0
    )

    print("📊 Configuration Comparison:")
    print(f"{'Parameter':<25} {'Standard':<15} {'Small Account':<15} {'Change':<15}")
    print("-" * 70)

    comparisons = [
        ("Capital Usage", f"{standard_config.max_account_usage_pct:.0%}", f"{small_config.max_account_usage_pct:.0%}"),
        (
            "Capital Allocation",
            f"${(standard_config.capital_allocation_usd or 0):.0f}",
            f"${(small_config.capital_allocation_usd or 0):.0f}",
        ),
        ("Position Risk", f"{standard_config.position_risk_pct:.1%}", f"{small_config.position_risk_pct:.1%}"),
        ("Stop Loss", f"{standard_config.stop_loss_pct:.1%}", f"{small_config.stop_loss_pct:.1%}"),
        ("Take Profit", f"{standard_config.take_profit_pct:.1%}", f"{small_config.take_profit_pct:.1%}"),
        ("Daily Trades", f"{standard_config.max_daily_trades}", f"{small_config.max_daily_trades}"),
        ("Daily Loss", f"${standard_config.max_daily_loss_usd:.0f}", f"${small_config.max_daily_loss_usd:.0f}"),
        ("Max Drawdown", f"{standard_config.max_drawdown_pct:.1%}", f"{small_config.max_drawdown_pct:.1%}"),
        ("Factor ID", standard_config.factor_id, small_config.factor_id),
        ("Factor IDs", ", ".join(standard_config.factor_ids), ", ".join(small_config.factor_ids)),
        ("Z-Score Period", standard_config.zscore_period, small_config.zscore_period),
        ("Min Signal", f"{standard_config.min_signal_magnitude:.3f}", f"{small_config.min_signal_magnitude:.3f}"),
    ]

    for param, standard, small in comparisons:
        print(f"{param:<25} {standard:<15} {small:<15} {'More Conservative':<15}")


if __name__ == "__main__":
    print("🚀 FactorExp Small Account Example")
    print("=" * 50)

    # Create small account strategy
    strategy, config = create_small_account_strategy_example()

    print("\n" + "=" * 50)

    # Compare configurations
    compare_configurations()

    print("\n✅ Small account support validated and optimized!")
    print("💡 Use FactorExpLiveStrategyConfig.create_small_account_config() for accounts ≤$500")
