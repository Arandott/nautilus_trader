#!/usr/bin/env python3
"""
FactorExp Live Trading Main Program

Entry point for the FactorExp live trading system with Nautilus Trader.
Integrates portfolio monitoring, risk management, and FactorExp strategies.
"""

import asyncio
import os
import sys
from pathlib import Path


# Add project root to Python path
project_root = Path(__file__).parent
repo_root = project_root.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(repo_root))

# Local imports
from factorexp_live_trading.config.security import SecureConfigManager
from factorexp_live_trading.strategies.factorexp_live_strategy import FactorExpLiveStrategy

from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance.factories import BinanceLiveExecClientFactory
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class FactorExpTradingSystem:
    """
    Main FactorExp trading system coordinator.
    
    Manages the complete lifecycle of live trading including:
    - API credential management
    - Trading node configuration
    - Strategy deployment
    - Portfolio and risk monitoring
    - Alert management
    """

    def __init__(self, instruments: list[str] = None, account_size_usd: float = None):
        """
        Initialize the trading system with user-configurable parameters.
        
        Parameters
        ----------
        instruments : List[str], optional
            List of instruments to trade (e.g., ["BTCUSDT-PERP.BINANCE"])
            If None, uses default instruments
        account_size_usd : float, optional
            Account size in USD for small account optimization
            If None, uses standard configuration
        """
        # User-configurable settings using StrategyConfig architecture
        self.instruments = instruments or self._get_default_instruments()
        self.account_size_usd = account_size_usd or self._detect_account_size()
        self.trading_node: TradingNode = None
        self.strategies: dict[str, Strategy] = {}

        # Native monitoring is handled by strategies using official patterns

        # System state
        self.is_running = False
        self.api_credentials: dict = {}
        self._config_manager: SecureConfigManager | None = None
        self._factor_params: dict | None = None

        # Data request tracking to prevent duplicate API calls
        self._requested_bar_types: set = set()

    def _get_default_instruments(self) -> list[str]:
        """Get default trading instruments."""
        # Check environment variable for backward compatibility
        instruments_env = os.getenv("TRADING_INSTRUMENTS", "")

        if instruments_env:
            # Parse comma-separated instruments
            instruments = [inst.strip() for inst in instruments_env.split(",") if inst.strip()]
            print(f"📊 User-configured instruments from env: {instruments}")
            return instruments
        else:
            # Default instruments
            default_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
            print(f"📊 Using default instruments: {default_instruments}")
            return default_instruments

    def _detect_account_size(self) -> float:
        """Detect account size from environment variable for backward compatibility."""
        account_size_env = os.getenv("ACCOUNT_SIZE_USD", "")
        try:
            if account_size_env and account_size_env.lower() not in ["", "standard"]:
                account_size = float(account_size_env)
                print(f"💰 Account size from env: ${account_size:.0f}")
                return account_size
        except ValueError:
            pass

        print("💰 Using standard account configuration")
        return None

    async def initialize(self) -> bool:
        """
        Initialize the trading system.
        
        Returns
        -------
        bool
            True if initialization successful
        """
        print("🚀 Initializing FactorExp Live Trading System...")

        try:
            # Step 0: Setup data directory for organized file storage
            self._setup_data_directory()

            # Step 1: Load and validate API credentials
            if not await self._load_credentials():
                return False

            # Step 2: Create trading node configuration with precision instrument loading
            from factorexp_live_trading.config.trading_config import create_trading_node_config
            node_config = create_trading_node_config(self.api_credentials, self.instruments)

            # Step 3: Create and configure trading node
            self.trading_node = TradingNode(config=node_config)

            # Step 3.5: Register Binance client factories
            from nautilus_trader.adapters.binance import BINANCE
            self.trading_node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
            self.trading_node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)

            # Native monitoring is handled by strategies using official patterns

            # Step 5: Create and configure strategies
            await self._initialize_strategies()

            print("✅ FactorExp Trading System initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False

    def _setup_data_directory(self):
        """Setup data and log directories for organized file storage."""
        data_dir = Path("./data")
        data_dir.mkdir(exist_ok=True)

        # Also create logs directory for application logs
        logs_dir = Path("./data/logs")
        logs_dir.mkdir(exist_ok=True)

        print(f"📁 Data directory ready: {data_dir.absolute()}")
        print(f"📋 Logs directory ready: {logs_dir.absolute()}")

    async def _load_credentials(self) -> bool:
        """Load and validate API credentials."""
        print("🔐 Loading API credentials...")

        try:
            # Use SecureConfigManager to load credentials
            project_root = Path(__file__).parent
            self._config_manager = SecureConfigManager(project_root)
            self.api_credentials = self._config_manager.get_api_credentials(use_encrypted=False)

            # Validate credentials using the config manager
            self._config_manager.validate_credentials(self.api_credentials)

            # Cache factor configuration parameters for strategy initialization
            try:
                self._factor_params = self._config_manager.get_factorexp_parameters()
            except Exception as exc:
                print(f"⚠️  Failed to load FactorExp configuration parameters: {exc}")
                self._factor_params = None

            trading_mode = "TESTNET" if self.api_credentials["testnet"] else "LIVE"
            print(f"✅ API credentials loaded - Mode: {trading_mode}")
            return True

        except Exception as e:
            print(f"❌ Failed to load credentials: {e}")
            return False


    async def _initialize_strategies(self):
        """Initialize and configure trading strategies with StrategyConfig architecture."""
        print("🧠 Initializing FactorExp strategies with StrategyConfig architecture...")

        # Import FactorExpLiveStrategyConfig locally to avoid dependency issues
        from factorexp_live_trading.config.strategy_config import FactorExpLiveStrategyConfig

        factor_params = self._factor_params or {}
        if not factor_params:
            factor_params = {
                "factor_config_path": "../factorexp_backtest/configs/factors.yaml",
                "factor_id": "vwap_return_std",
                "zscore_period": 5760,
                "clip_min": -2.0,
                "clip_max": 2.0,
                "min_signal_magnitude": 0.05,
            }

        for instrument_str in self.instruments:
            instrument_id = InstrumentId.from_str(instrument_str)
            bar_type = BarType.from_str(f"{instrument_str}-15-MINUTE-LAST-INTERNAL")

            # Create strategy configuration using official FactorExpLiveStrategyConfig
            if self.account_size_usd and self.account_size_usd <= 500:
                # Use optimized configuration for small accounts
                strategy_config = FactorExpLiveStrategyConfig.create_small_account_config(
                    instrument_id=instrument_id,
                    bar_type=bar_type,
                    account_size_usd=self.account_size_usd,
                    **factor_params,
                )
                print(f"📊 Small account config for {instrument_str} (${self.account_size_usd:.0f}):")
            else:
                # Use standard configuration
                strategy_config = FactorExpLiveStrategyConfig(
                    instrument_id=instrument_id,
                    bar_type=bar_type,
                    **factor_params,
                )
                print(f"📊 Standard config for {instrument_str}:")

            # Display configuration
            print(f"  Max account usage: {strategy_config.max_account_usage_pct:.0%}")
            print(f"  Max absolute exposure: ${strategy_config.max_absolute_exposure:,.0f}")
            print(f"  Position risk: {strategy_config.position_risk_pct:.1%}")
            print(f"  Stop loss: {strategy_config.stop_loss_pct:.1%}")
            print(
                f"  Factor: {strategy_config.factor_id} | "
                f"ZScore={strategy_config.zscore_period} | "
                f"Clip=({strategy_config.clip_min}, {strategy_config.clip_max}) | "
                f"MinSignal={strategy_config.min_signal_magnitude}"
            )
            print(f"  Factor config path: {strategy_config.factor_config_path}")

            # Create strategy instance
            strategy = FactorExpLiveStrategy(strategy_config)

            # Native monitoring is handled by the strategy itself using official patterns

            # Check if we've already requested historical data for this bar type
            bar_type_str = str(bar_type)
            should_request_historical = bar_type_str not in self._requested_bar_types
            if should_request_historical:
                self._requested_bar_types.add(bar_type_str)
                print(f"📊 Strategy for {instrument_str} will request historical data")
            else:
                print(f"📊 Strategy for {instrument_str} will skip historical data (already requested)")

            # Set historical data request flag
            strategy._should_request_historical_data = should_request_historical

            # Register strategy with trading node
            self.trading_node.trader.add_strategy(strategy)
            self.strategies[instrument_str] = strategy

        print(f"✅ {len(self.strategies)} FactorExp strategies initialized")

    def prepare_trading(self):
        """Prepare the trading system (build but don't run)."""
        if not self.trading_node:
            print("❌ Trading system not initialized")
            return False

        print("🚀 Preparing live trading...")
        self.is_running = True

        try:
            # Build the trading node (but don't run it yet)
            if not self.trading_node.is_built():
                self.trading_node.build()

            # Market data subscription is handled automatically by the framework
            # when strategies are added and the trading node is started

            print("✅ Live trading prepared successfully")
            print(f"📈 Will monitor {len(self.instruments)} instruments:")
            for instrument in self.instruments:
                print(f"  • {instrument}")

            print("\n📊 Strategy Status:")
            for instrument, strategy in self.strategies.items():
                summary = strategy.get_strategy_summary()
                exposure = summary.get("current_exposure_usd")
                balance_used = summary.get("balance_used_pct")
                indicator_ready = summary.get("factor", {}).get("indicator_ready", False)

                exposure_str = f"{exposure:.2f} USD" if isinstance(exposure, (int, float)) else str(exposure)
                balance_str = f"{balance_used:.2f}%" if isinstance(balance_used, (int, float)) else str(balance_used)

                print(
                    f"  • {instrument}: exposure={exposure_str}, "
                    f"balance_used={balance_str} | Indicator Ready: {indicator_ready}"
                )

            return True

        except Exception as e:
            print(f"❌ Failed to prepare trading: {e}")
            self.is_running = False
            return False

    async def run_trading(self):
        """Run the trading node (blocking until shutdown)."""
        if not self.trading_node or not self.trading_node.is_built():
            print("❌ Trading node not prepared")
            return

        print("🚀 Starting trading node...")
        print("✅ System running - monitoring via strategies")
        print("📊 Check logs for portfolio metrics")
        print("🛑 Press Ctrl+C to shutdown")

        # This blocks until the node is stopped (handles signals internally)
        await self.trading_node.run_async()

    async def stop_trading(self):
        """Stop the live trading system with timeout-based forced termination."""
        if not self.is_running:
            return

        print("🛑 Stopping live trading...")
        self.is_running = False

        try:
            # Shutdown notifications handled by strategies using native logging

            # Native monitoring timers are handled by the framework automatically

            # CRITICAL FIX: Stop trading node with timeout-based forced termination
            if self.trading_node and self.trading_node.is_running():
                print("🛑 Attempting graceful TradingNode shutdown...")
                try:
                    # Try graceful shutdown with 10-second timeout
                    await asyncio.wait_for(self.trading_node.stop_async(), timeout=10.0)
                    print("✅ TradingNode stopped gracefully")
                except TimeoutError:
                    print("⚠️ TradingNode graceful shutdown timed out - forcing termination...")

                    # Force cancel all pending tasks
                    pending_tasks = [task for task in asyncio.all_tasks() if not task.done()]
                    if pending_tasks:
                        print(f"🛑 Cancelling {len(pending_tasks)} pending tasks...")
                        for task in pending_tasks:
                            if not task.cancelled():
                                task.cancel()

                        # Wait briefly for task cancellation
                        try:
                            await asyncio.wait_for(asyncio.gather(*pending_tasks, return_exceptions=True), timeout=3.0)
                        except TimeoutError:
                            print("⚠️ Some tasks did not cancel within timeout")

                    print("🛑 FORCE SHUTDOWN: TradingNode did not stop gracefully")
                    # At this point, the process will exit via main() cleanup

            print("✅ Trading system stopped successfully")

        except Exception as e:
            print(f"❌ Error during shutdown: {e}")
            print("🛑 FORCE SHUTDOWN due to error")

    # Monitoring functionality removed - using native strategy-level monitoring instead

    def get_system_status(self) -> dict:
        """Get comprehensive system status."""
        return {
            "is_running": self.is_running,
            "strategies_count": len(self.strategies),
            "instruments": self.instruments,
            "account_size_usd": self.account_size_usd,
            "strategies_status": {
                inst: strategy.get_strategy_summary()
                for inst, strategy in self.strategies.items()
            }
        }


async def main(instruments: list[str] = None, account_size_usd: float = None):
    """Main entry point for the FactorExp trading system."""
    print("=" * 60)
    print("🚀 FactorExp Live Trading System")
    print("   Advanced Quantitative Trading with Nautilus Trader")
    print("   Using StrategyConfig Architecture")
    print("=" * 60)

    # Create trading system with user-configurable parameters
    trading_system = FactorExpTradingSystem(
        instruments=instruments,
        account_size_usd=account_size_usd
    )

    try:
        # Initialize system
        if not await trading_system.initialize():
            print("❌ System initialization failed")
            return

        # Prepare trading (build but don't run)
        if not trading_system.prepare_trading():
            print("❌ Trading preparation failed")
            return

        # Run the trading node (blocks until shutdown, handles signals internally)
        # This follows the official Nautilus Trader pattern from examples/live/betfair/betfair.py
        await trading_system.run_trading()

    except KeyboardInterrupt:
        print("\n🛑 Shutdown signal received")
    except Exception as e:
        print(f"❌ System error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            print("🛑 System cleanup...")
            await trading_system.stop_trading()
            if trading_system.trading_node:
                trading_system.trading_node.dispose()
            print("👋 FactorExp Trading System shutdown complete")
        except Exception as e:
            print(f"🛑 Cleanup error: {e}")
            import os
            os._exit(1)  # Force exit if cleanup fails


if __name__ == "__main__":
    # Set up environment
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent))

    # Example: User-configurable trading parameters
    # Uncomment and modify these lines to customize your trading:

    # Custom instruments (perpetual contracts to trade)
    # custom_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE", "SOLUSDT-PERP.BINANCE"]

    # Custom account size for small account optimization
    # custom_account_size = 200.0  # USD

    # Run with custom parameters:
    # asyncio.run(main(instruments=custom_instruments, account_size_usd=custom_account_size))

    # Run with default parameters (or environment variables for backward compatibility)
    asyncio.run(main())
