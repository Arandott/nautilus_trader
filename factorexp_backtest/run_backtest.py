#!/usr/bin/env python3
"""
Run configuration-based factor backtesting.

This script runs backtests using factor configurations from YAML files,
with standardized Clip(Zscore(...)) expressions that directly map to
position sizing under 2x leverage.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


# Add nautilus_trader to path
nautilus_path = Path(__file__).parent.parent / "nautilus_trader"
if nautilus_path.exists():
    sys.path.insert(0, str(nautilus_path))

from factorexp_backtest.configs import FactorConfigLoader
from factorexp_backtest.loaders import FeatherBarLoader
from factorexp_backtest.strategies import SingleFactorStrategy
from factorexp_backtest.strategies import SingleFactorStrategyConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider


def list_available_factors(config_path: Path):
    """
    List all available factors from the configuration file.

    Parameters
    ----------
    config_path : Path
        Path to the configuration file.
    """
    loader = FactorConfigLoader(config_path)

    print("\n" + "=" * 60)
    print("Available Factors")
    print("=" * 60)

    for factor_id in loader.list_factors():
        factor = loader.get_factor(factor_id)
        print(f"\n{factor_id}:")
        print(f"  Name: {factor.name}")
        print(f"  Description: {factor.description}")
        print(f"  Expression: {factor.expression[:50]}...")
        if factor.requires_extended:
            print("  ⚠️  Requires extended bar fields")


def check_extended_support() -> bool:
    """Check if extended bar support is available."""
    try:
        from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
        return bool(EXTENDED_BAR_FIELD_SPECS)
    except Exception:
        return False


def setup_backtest_engine(
    data_path: Path,
    start_date: str,
    end_date: str,
    bar_type: str = "15-MINUTE",
) -> BacktestEngine:
    """
    Set up the backtest engine with configuration.

    Parameters
    ----------
    data_path : Path
        Path to the data directory.
    start_date : str
        Start date for the backtest (YYYY-MM-DD).
    end_date : str
        End date for the backtest (YYYY-MM-DD).
    bar_type : str
        Bar type specification (e.g., "15-MINUTE", "1-HOUR").

    Returns
    -------
    BacktestEngine
        Configured backtest engine.
    """
    # Create engine configuration
    config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        logging=LoggingConfig(log_level="INFO"),
    )

    # Create backtest engine
    engine = BacktestEngine(config=config)

    # Add venue
    venue = Venue("BINANCE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=BTC,
        starting_balances=[
            Money(10_000, USDT),
            Money(1, BTC),
        ],
    )

    # Add instrument
    provider = TestInstrumentProvider()
    btcusdt = provider.btcusdt_binance()
    engine.add_instrument(btcusdt)

    # Load data with extended fields
    loader = FeatherBarLoader(data_path)

    # Check if extended bar support is available
    if loader._has_extended_bar:
        print("✅ Extended bar support detected - amt fields will be available")
    else:
        print("⚠️  Extended bar support not detected - using standard OHLCV only")

    # Load bar data - Convert types properly
    import pandas as pd

    # Create InstrumentId from string
    instrument_id_str = "BTCUSDT.BINANCE"
    instrument_symbol = Symbol(instrument_id_str.split(".")[0])
    instrument_venue = Venue(instrument_id_str.split(".")[1])
    instrument_id_obj = InstrumentId(symbol=instrument_symbol, venue=instrument_venue)

    bars = loader.load_bars(
        instrument_id=instrument_id_obj,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
    )

    if bars:
        print(f"Loaded {len(bars)} bars from {start_date} to {end_date}")

        # Check first bar for extended fields
        if bars and loader._has_extended_bar:
            first_bar = bars[0]
            amt = getattr(first_bar, "amt", None)
            if amt is not None:
                print(f"✅ First bar has amt value: {amt:,.2f}")
            else:
                print("⚠️  First bar doesn't have amt value")

        # Add data to engine
        engine.add_data(bars)
    else:
        print(f"❌ No data loaded for period {start_date} to {end_date}")
        return None

    return engine


def main():
    """Main entry point for the backtest."""
    parser = argparse.ArgumentParser(
        description="Run single-factor backtesting with standardized Clip(Zscore(...)) expressions"
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path(__file__).parent / "configs" / "factors.yaml",
        help="Path to factor configuration YAML file",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Path to data directory",
    )
    parser.add_argument(
        "--factor",
        type=str,
        default="amt_momentum",
        help="Factor ID from configuration file",
    )
    parser.add_argument(
        "--list-factors",
        action="store_true",
        help="List available factors and exit",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-01-31",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--bar-type",
        type=str,
        default="15-MINUTE",
        help="Bar type (e.g., 15-MINUTE, 1-HOUR)",
    )
    parser.add_argument(
        "--position-scale",
        type=float,
        default=1.0,
        help="Position scale factor (1.0 = use factor values directly)",
    )

    args = parser.parse_args()

    # Check if config file exists
    if not args.config_path.exists():
        print(f"❌ Configuration file not found: {args.config_path}")
        return 1

    # List factors if requested
    if args.list_factors:
        list_available_factors(args.config_path)
        return 0

    print("=" * 60)
    print("Single-Factor Backtesting")
    print("=" * 60)

    # Load configuration to validate strategy
    config_loader = FactorConfigLoader(args.config_path)

    # Check if factor exists
    if args.factor not in config_loader.list_factors():
        print(f"❌ Factor '{args.factor}' not found in configuration")
        print(f"Available factors: {', '.join(config_loader.list_factors())}")
        return 1

    # Check extended support
    has_extended = check_extended_support()
    available_factors = config_loader.validate_extended_support(has_extended)

    if args.factor not in available_factors:
        print(f"❌ Factor '{args.factor}' requires extended bar support which is not available")
        print(f"Available factors: {', '.join(available_factors)}")
        return 1

    # Get factor details
    factor_config = config_loader.get_factor(args.factor)
    print(f"\nFactor: {factor_config.name}")
    print(f"Description: {factor_config.description}")
    print(f"Expression: {factor_config.expression}")
    if factor_config.requires_extended:
        print("⚠️  Requires extended bar fields")

    # Display defaults
    defaults = config_loader.get_defaults()
    print("\nDefault Settings:")
    print(f"  Zscore Period: {defaults.get('zscore_period', 5760)} bars")
    print(f"  Rebalance Interval: {defaults.get('rebalance_interval', 30)} bars")

    # Display risk management settings
    if config_loader.risk_config:
        risk = config_loader.risk_config
        print("\nRisk Management:")
        print(f"  Max Position Size: {risk.max_position_size}x")
        print(f"  Stop Loss: {risk.stop_loss:.1%}")
        print(f"  Min Rebalance Interval: {risk.min_rebalance_interval} bars")
        print(f"  Max Rebalance Interval: {risk.max_rebalance_interval} bars")

    # Display execution settings
    if config_loader.execution_config:
        exec_cfg = config_loader.execution_config
        print("\nExecution Settings:")
        print(f"  Slippage: {exec_cfg.slippage_bps} bps")
        print(f"  Commission: {exec_cfg.commission_bps} bps")
        print(f"  Min Order Size: {exec_cfg.min_order_size}")
        print(f"  Max Order Size: {exec_cfg.max_order_size}")

    # Set up backtest engine
    engine = setup_backtest_engine(
        data_path=args.data_path,
        start_date=args.start_date,
        end_date=args.end_date,
        bar_type=args.bar_type,
    )

    if not engine:
        print("Failed to set up backtest engine")
        return 1

    # Create strategy configuration
    bar_type_str = f"BTCUSDT.BINANCE-{args.bar_type}-LAST-EXTERNAL"
    strategy_cfg = SingleFactorStrategyConfig(
        instrument_id="BTCUSDT.BINANCE",
        bar_type=bar_type_str,
        config_path=str(args.config_path),
        factor_id=args.factor,
        position_scale=args.position_scale,
    )

    # Add strategy to engine
    strategy = SingleFactorStrategy(config=strategy_cfg)
    engine.add_strategy(strategy)

    print("\n" + "-" * 60)
    print("Running backtest...")
    print(f"Factor: {args.factor}")
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Bar Type: {args.bar_type}")
    print(f"Position Scale: {args.position_scale}")
    print("-" * 60)

    # Run backtest
    engine.run()

    # Print results
    print("\n" + "=" * 60)
    print("Backtest Results")
    print("=" * 60)

    # Get portfolio statistics
    account = engine.trader.generate_account_report(Venue("BINANCE"))
    print("\nAccount Statistics:")
    print(f"  Final Balance (USDT): {account.balances_total.get(USDT, 0):,.2f}")
    print(f"  Final Balance (BTC): {account.balances_total.get(BTC, 0):.8f}")

    # Calculate returns
    initial_usdt = 10_000
    final_usdt = float(account.balances_total.get(USDT, 0))
    returns_pct = ((final_usdt - initial_usdt) / initial_usdt) * 100
    print(f"  Total Return: {returns_pct:.2f}%")

    # Get positions report
    positions = engine.trader.generate_positions_report()
    print("\nPosition Statistics:")
    print(f"  Total Positions: {positions.total_count}")
    if positions.total_count > 0:
        print(f"  Win Rate: {positions.win_rate:.2%}" if positions.win_rate else "  Win Rate: N/A")
        print(f"  Avg Win: {positions.avg_win:,.2f} USDT" if positions.avg_win else "  Avg Win: N/A")
        print(f"  Avg Loss: {positions.avg_loss:,.2f} USDT" if positions.avg_loss else "  Avg Loss: N/A")

    # Get order statistics
    orders = engine.trader.generate_orders_report()
    print("\nOrder Statistics:")
    print(f"  Total Orders: {orders.total_count}")
    if orders.total_count > 0:
        print(f"  Fill Rate: {orders.fill_rate:.2%}" if orders.fill_rate else "  Fill Rate: N/A")

    # Calculate Sharpe ratio (simplified)
    if positions.total_count > 0:
        # This is a simplified calculation - real Sharpe would need returns series
        avg_return = returns_pct / 100
        # Assume annualized for the period
        periods_per_year = 365 / ((datetime.fromisoformat(args.end_date) -
                                   datetime.fromisoformat(args.start_date)).days)
        annualized_return = avg_return * periods_per_year
        print("\nRisk Metrics:")
        print(f"  Annualized Return: {annualized_return * 100:.2f}%")

    print("\n" + "=" * 60)
    print("Backtest Complete")
    print("=" * 60)

    # Dispose engine
    engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(main())
