#!/usr/bin/env python3
"""
FactorExp Live Trading Startup Script

Professional startup script with comprehensive pre-flight checks, 
environment validation, and support for both standard and small account configurations.
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Optional

# Add project paths
project_root = Path(__file__).parent
nautilus_root = project_root.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(nautilus_root))

from main import FactorExpTradingSystem


def check_environment():
    """Pre-flight environment checks for new StrategyConfig architecture."""
    print("🔍 Running pre-flight checks...")
    
    checks = []
    
    # Check environment file
    env_file = project_root / ".env"
    if env_file.exists():
        checks.append(("✅", "Environment file found"))
    else:
        checks.append(("⚠️", "Environment file missing (.env) - will use defaults"))
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
            checks.append(("❌", f"Critical API credential {var} missing"))
            return False
    
    # Check optional environment variables
    optional_vars = {
        "TRADING_MODE": "testnet",
        "LOG_LEVEL": "INFO",
        "ACCOUNT_SIZE_USD": "Standard account configuration"
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
        checks.append(("❌", f"Python version {sys.version_info.major}.{sys.version_info.minor} too old (need 3.9+)"))
        return False
    
    # Check nautilus_trader import
    try:
        import nautilus_trader
        checks.append(("✅", f"Nautilus Trader {nautilus_trader.__version__} imported"))
    except ImportError:
        checks.append(("❌", "Nautilus Trader not installed"))
        return False
    
    # Check factorexp availability
    try:
        from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
        checks.append(("✅", "FactorExp indicators available"))
    except ImportError:
        checks.append(("❌", "FactorExp indicators not available"))
        return False
        
    # Check new configuration system
    try:
        from config.strategy_config import FactorExpLiveStrategyConfig
        checks.append(("✅", "New StrategyConfig architecture available"))
    except ImportError:
        checks.append(("❌", "StrategyConfig system not available"))
        return False
    
    # Print all checks
    for status, message in checks:
        print(f"  {status} {message}")
    
    return all(status in ["✅", "ℹ️", "⚠️"] for status, _ in checks)


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
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            return True
        else:
            print("ℹ️ No .env file found - using system environment and defaults")
            return True


def show_configuration():
    """Display current configuration using new StrategyConfig architecture."""
    print("\n📋 Current Configuration (StrategyConfig Architecture):")
    
    # Core trading settings
    trading_mode = os.getenv('TRADING_MODE', 'testnet')
    account_size = os.getenv('ACCOUNT_SIZE_USD', 'Standard')
    
    print(f"  🔧 Trading Mode: {trading_mode}")
    print(f"  💰 Account Configuration: {account_size}")
    
    # Account type detection
    try:
        account_size_float = float(account_size) if account_size != 'Standard' else 0
        if account_size_float > 0 and account_size_float <= 500:
            print(f"  📊 Account Type: Small Account (≤$500) - Optimized settings enabled")
        else:
            print(f"  📊 Account Type: Standard Account")
    except ValueError:
        print(f"  📊 Account Type: Standard Account")
    
    # New StrategyConfig parameters (defaults)
    print(f"\n  🎯 Strategy Configuration:")
    print(f"    • Capital Usage: 80% (60% for small accounts)")
    print(f"    • Position Risk: 2% (1.5% for small accounts)")  
    print(f"    • Stop Loss: 1.5% (1.2% for small accounts)")
    print(f"    • Max Daily Trades: 20 (10 for small accounts)")
    
    # Alert settings
    print(f"\n  🔔 Alert Configuration:")
    print(f"    • Email Alerts: {'Enabled' if os.getenv('ENABLE_EMAIL_ALERTS', 'false').lower() == 'true' else 'Disabled'}")
    print(f"    • Webhook Alerts: {'Enabled' if os.getenv('ENABLE_WEBHOOK_ALERTS', 'false').lower() == 'true' else 'Disabled'}")
    
    # System settings
    print(f"\n  ⚙️ System Settings:")
    print(f"    • Log Level: {os.getenv('LOG_LEVEL', 'INFO')}")
    print(f"    • Configuration: Type-safe StrategyConfig with validation")
    
    # Warning about deprecated variables
    deprecated_vars = ['MAX_POSITION_SIZE_BTC', 'MAX_DAILY_LOSS_USD', 'MAX_DRAWDOWN_PCT']
    deprecated_found = [var for var in deprecated_vars if os.getenv(var)]
    
    if deprecated_found:
        print(f"\n  ⚠️ Deprecated Environment Variables Detected:")
        for var in deprecated_found:
            print(f"    • {var} - Now configured via StrategyConfig class")
        print(f"    Please migrate to new configuration system.")


def detect_and_configure_account_type() -> Optional[float]:
    """Detect account type and offer configuration options."""
    account_size_env = os.getenv('ACCOUNT_SIZE_USD', '')
    
    # Try to get account size from environment
    try:
        if account_size_env and account_size_env != 'Standard':
            account_size = float(account_size_env)
            print(f"\n💰 Account size detected: ${account_size:.0f}")
        else:
            account_size = None
    except ValueError:
        account_size = None
    
    # If no account size specified, ask user
    if account_size is None:
        print("\n💰 Account Configuration:")
        print("  1. Standard Account (>$500) - Default settings")
        print("  2. Small Account (≤$500) - Conservative optimized settings")
        print("  3. Custom Amount - Specify your account size")
        
        while True:
            try:
                choice = input("\nSelect account type (1/2/3): ").strip()
                
                if choice == '1':
                    account_size = None  # Use standard configuration
                    print("✅ Using standard account configuration")
                    break
                elif choice == '2':
                    account_size = 200.0  # Default small account size
                    print("✅ Using small account optimized configuration")
                    break
                elif choice == '3':
                    size_input = input("Enter your account size in USD: $").strip()
                    account_size = float(size_input)
                    if account_size <= 500:
                        print(f"✅ Using small account configuration for ${account_size:.0f}")
                    else:
                        print(f"✅ Using standard account configuration for ${account_size:.0f}")
                    break
                else:
                    print("❌ Invalid choice. Please enter 1, 2, or 3.")
            except ValueError:
                print("❌ Invalid amount. Please enter a valid number.")
            except KeyboardInterrupt:
                print("\n❌ Configuration cancelled")
                return None
    
    return account_size


def confirm_trading_mode():
    """Confirm trading mode with user."""
    trading_mode = os.getenv('TRADING_MODE', 'testnet')
    
    if trading_mode.lower() == 'live':
        print("\n⚠️  WARNING: LIVE TRADING MODE ENABLED ⚠️")
        print("   This will use real money and real trades!")
        print("   Make sure you understand the risks.")
        print("   Ensure you have tested thoroughly in TESTNET mode first.")
        
        response = input("\nType 'CONFIRM' to proceed with live trading: ")
        if response != 'CONFIRM':
            print("❌ Live trading cancelled")
            return False
    
    else:
        print(f"\n✅ Using TESTNET mode - safe for testing")
    
    return True


async def main():
    """Main startup routine with new StrategyConfig architecture support."""
    print("=" * 60)
    print("🚀 FactorExp Live Trading System - Professional Startup")
    print("   🎯 StrategyConfig Architecture | 💰 Small Account Support")
    print("=" * 60)
    
    # Step 1: Load environment
    if not load_environment():
        return
    
    # Step 2: Run pre-flight checks  
    if not check_environment():
        print("\n❌ Pre-flight checks failed. Please fix the issues above.")
        return
    
    # Step 3: Account configuration
    account_size = detect_and_configure_account_type()
    if account_size is None and 'ACCOUNT_SIZE_USD' not in os.environ:
        # User cancelled or error occurred
        print("❌ Account configuration required")
        return
    
    # Set account size in environment for main system
    if account_size is not None:
        os.environ['ACCOUNT_SIZE_USD'] = str(account_size)
    
    # Step 4: Show final configuration
    show_configuration()
    
    # Step 5: Confirm trading mode
    if not confirm_trading_mode():
        return
    
    # Step 6: Start trading system
    print("\n🚀 Starting FactorExp Trading System...")
    print("📊 Using new StrategyConfig architecture with type-safe configurations")
    
    try:
        # Import and run main system
        from main import main as run_trading_system
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