#!/usr/bin/env python3
"""
FactorExp Live Trading Startup Script

Professional startup script with comprehensive pre-flight checks and
environment validation for the StrategyConfig-based live trading system.
"""

import asyncio
import os
import sys
from pathlib import Path


# Add project paths
project_root = Path(__file__).parent
nautilus_root = project_root.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(nautilus_root))



def check_environment():
    """Pre-flight environment checks for new StrategyConfig architecture."""
    print("🔍 Running pre-flight checks...")

    checks = []

    failures = []

    # Check environment file
    env_file = project_root / ".env"
    if env_file.exists():
        checks.append(("✅", "Environment file found"))
    else:
        warning_msg = "Environment file missing (.env) - will use defaults"
        checks.append(("⚠️", warning_msg))
        failures.append(("⚠️", warning_msg))
        # Not a failure anymore since we have typed configurations

    # Check essential environment variables (only critical ones)
    required_vars = [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
    ]

    for var in required_vars:
        if os.getenv(var):
            checks.append(("✅", f"API credential {var} configured"))
        else:
            msg = f"Critical API credential {var} missing"
            checks.append(("❌", msg))
            failures.append(("❌", msg))

    # Check optional environment variables
    optional_vars = {
        "TRADING_MODE": "testnet",
        "LOG_LEVEL": "INFO",
        "FACTOREXP_CAPITAL_ALLOCATION_USD": "StrategyConfig fallback",
        "FACTOREXP_TARGET_NOTIONAL_USD": "Derived from margin × leverage",
        "FACTOREXP_MAX_LEVERAGE": "Strategy/risk config default",
    }

    for var, default in optional_vars.items():
        if os.getenv(var):
            checks.append(("✅", f"Optional setting {var} configured"))
        else:
            checks.append(("ℹ️", f"Using default {var}: {default}"))

    # Check Python version
    if sys.version_info >= (3, 9):
        checks.append(("✅", f"Python version {sys.version_info.major}.{sys.version_info.minor} OK"))
    else:
        msg = f"Python version {sys.version_info.major}.{sys.version_info.minor} too old (need 3.9+)"
        checks.append(("❌", msg))
        failures.append(("❌", msg))

    # Check nautilus_trader import
    try:
        import nautilus_trader
        checks.append(("✅", f"Nautilus Trader {nautilus_trader.__version__} imported"))
    except ImportError:
        msg = "Nautilus Trader not installed"
        checks.append(("❌", msg))
        failures.append(("❌", msg))

    # Check factorexp availability
    try:
        from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
        checks.append(("✅", "FactorExp indicators available"))
    except ImportError:
        msg = "FactorExp indicators not available"
        checks.append(("❌", msg))
        failures.append(("❌", msg))

    # Check new configuration system
    try:
        from factorexp_live_trading.config.strategy_config import FactorExpLiveStrategyConfig  # noqa: F401
        checks.append(("✅", "New StrategyConfig architecture available"))
    except ImportError as exc:
        msg = f"StrategyConfig system not available ({exc})"
        checks.append(("❌", msg))
        failures.append(("❌", msg))

    # Print all checks
    for status, message in checks:
        print(f"  {status} {message}")

    if failures:
        print("\n❌ Pre-flight checks detected issues:")
        for status, message in failures:
            print(f"  {status} {message}")
        return False

    return True


def load_environment():
    """Load environment variables using python-dotenv."""
    env_file = project_root / ".env"

    try:
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file)
            print(f"✅ Environment loaded from {env_file}")
        else:
            print("ℹ️ No .env file found - using system environment and defaults")
        return True
    except ImportError:
        print("⚠️ python-dotenv not found, using manual parsing...")
        # Fallback to manual parsing if dotenv not available
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
            return True
        else:
            print("ℹ️ No .env file found - using system environment and defaults")
            return True


def show_configuration():
    """Display current configuration using new StrategyConfig architecture."""
    print("\n📋 Current Configuration (StrategyConfig Architecture):")

    trading_mode = os.getenv("TRADING_MODE", "testnet")
    print(f"  🔧 Trading Mode: {trading_mode}")

    # Strategy defaults
    print("\n  🎯 Strategy Configuration:")
    print("    • Capital Usage ceiling: 80% of detected equity (configurable)")
    print("    • Margin budget: via FACTOREXP_CAPITAL_ALLOCATION_USD or StrategyConfig default")
    print("    • Target notional: via FACTOREXP_TARGET_NOTIONAL_USD or margin × leverage")
    print("    • Max leverage override: FACTOREXP_MAX_LEVERAGE (optional)")

    factor_config_path = os.getenv("FACTOREXP_CONFIG_PATH", "../factorexp_backtest/configs/factors.yaml")
    factor_id = os.getenv("FACTOREXP_FACTOR_ID", "vwap_return_std")
    zscore_period = os.getenv("FACTOREXP_ZSCORE_PERIOD", "5760")
    clip_min = os.getenv("FACTOREXP_CLIP_MIN", "-2.0")
    clip_max = os.getenv("FACTOREXP_CLIP_MAX", "2.0")
    min_signal = os.getenv("FACTOREXP_MIN_SIGNAL", "0.05")
    capital_allocation = os.getenv("FACTOREXP_CAPITAL_ALLOCATION_USD", "")
    target_notional = os.getenv("FACTOREXP_TARGET_NOTIONAL_USD", "")
    max_leverage = os.getenv("FACTOREXP_MAX_LEVERAGE", "")

    print("\n  🧮 FactorExp Alignment:")
    print(f"    • Factor Catalog: {factor_config_path}")
    print(f"    • Factor ID: {factor_id}")
    print(f"    • Z-Score Period: {zscore_period}")
    print(f"    • Clip Bounds: [{clip_min}, {clip_max}]")
    print(f"    • Min Signal Magnitude: {min_signal}")
    margin_msg = capital_allocation if capital_allocation else "Derived from StrategyConfig"
    target_notional_msg = target_notional if target_notional else "Derived from margin × leverage"
    leverage_msg = max_leverage if max_leverage else "Strategy/risk config default"
    print(f"    • Margin Allocation: {margin_msg}")
    print(f"    • Target Notional: {target_notional_msg}")
    print(f"    • Max Leverage Override: {leverage_msg}")
    print("    • ⚠️ 未消费字段: position_risk_pct / take_profit_pct / use_market_orders / "
          "max_daily_trades / max_daily_loss_usd / max_drawdown_pct")

    # Alert settings
    print("\n  🔔 Alert Configuration:")
    print(f"    • Email Alerts: {'Enabled' if os.getenv('ENABLE_EMAIL_ALERTS', 'false').lower() == 'true' else 'Disabled'}")
    print(f"    • Webhook Alerts: {'Enabled' if os.getenv('ENABLE_WEBHOOK_ALERTS', 'false').lower() == 'true' else 'Disabled'}")

    # System settings
    print("\n  ⚙️ System Settings:")
    print(f"    • Log Level: {os.getenv('LOG_LEVEL', 'INFO')}")
    print("    • Configuration: Type-safe StrategyConfig with validation")

    # Warning about deprecated variables
    deprecated_vars = ["MAX_POSITION_SIZE_BTC", "MAX_DAILY_LOSS_USD", "MAX_DRAWDOWN_PCT"]
    deprecated_found = [var for var in deprecated_vars if os.getenv(var)]

    if deprecated_found:
        print("\n  ⚠️ Deprecated Environment Variables Detected:")
        for var in deprecated_found:
            print(f"    • {var} - Now configured via StrategyConfig class")
        print("    Please migrate to new configuration system.")


def confirm_trading_mode():
    """Confirm trading mode with user."""
    trading_mode = os.getenv("TRADING_MODE", "testnet")

    if trading_mode.lower() == "live":
        print("\n⚠️  WARNING: LIVE TRADING MODE ENABLED ⚠️")
        print("   This will use real money and real trades!")
        print("   Make sure you understand the risks.")
        print("   Ensure you have tested thoroughly in TESTNET mode first.")

        response = input("\nType 'CONFIRM' to proceed with live trading: ")
        if response != "CONFIRM":
            print("❌ Live trading cancelled")
            return False

    else:
        print("\n✅ Using TESTNET mode - safe for testing")

    return True


async def main():
    """Main startup routine with new StrategyConfig architecture support."""
    print("=" * 60)
    print("🚀 FactorExp Live Trading System - Professional Startup")
    print("   🎯 StrategyConfig Architecture")
    print("=" * 60)

    # Step 1: Load environment
    if not load_environment():
        return

    # Step 2: Run pre-flight checks
    if not check_environment():
        print("\n❌ Pre-flight checks failed. Please fix the issues above.")
        return

    # Step 3: Show final configuration
    show_configuration()

    # Step 4: Confirm trading mode
    if not confirm_trading_mode():
        return

    # Step 5: Start trading system
    print("\n🚀 Starting FactorExp Trading System...")
    print("📊 Using new StrategyConfig architecture with type-safe configurations")

    try:
        # Import and run main system
        from factorexp_live_trading.main import main as run_trading_system
        await run_trading_system()

    except KeyboardInterrupt:
        print("\n🛑 Startup cancelled by user")
    except Exception as e:
        print(f"\n❌ Startup failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Use manual event loop to avoid conflicts with Nautilus Trader's uvloop usage
    # This prevents "Event loop stopped before Future completed" errors
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        finally:
            # Proper cleanup to avoid uvloop conflicts
            try:
                # Cancel any remaining tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    # Wait briefly for cancellation
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                loop.close()
    except Exception as e:
        print(f"❌ System error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
