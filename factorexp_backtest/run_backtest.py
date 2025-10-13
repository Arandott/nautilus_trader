#!/usr/bin/env python3
"""
Run configuration-based factor backtesting (Phase C).

This script runs backtests using factor configurations from YAML files,
with standardized Clip(ZScore(...)) expressions that directly map to
position sizing under 2x leverage.

Phase C additions:
- Multi-instrument×factor batch backtesting
- Parallel execution support
- Catalog and Feather data source support
- Results persistence to disk
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# Add nautilus_trader to path
nautilus_path = Path(__file__).parent.parent / "nautilus_trader"
if nautilus_path.exists():
    sys.path.insert(0, str(nautilus_path))

from factorexp_backtest.configs import BacktestConfigLoader
from factorexp_backtest.configs import RunConfig
from factorexp_backtest.loaders import FeatherBarLoader
from factorexp_backtest.loaders import create_catalog
from factorexp_backtest.strategies import SingleFactorStrategy
from factorexp_backtest.strategies import SingleFactorStrategyConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model import currencies
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider


def check_extended_support() -> bool:
    """Check if extended bar support is available."""
    try:
        from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
        return bool(EXTENDED_BAR_FIELD_SPECS)
    except Exception:
        return False


def get_currency_from_code(code: str):
    """
    Get currency object from currency code.

    Parameters
    ----------
    code : str
        Currency code (e.g., "BTC", "USDT", "ETH").

    Returns
    -------
    Currency
        Currency object.
    """
    # Try to get currency from module directly
    if hasattr(currencies, code):
        return getattr(currencies, code)

    # Fallback: Create currency from string
    return currencies.Currency.from_str(code)


def parse_money_value(value: Any) -> float:
    """Convert Money-like values or numeric strings to float for calculations."""
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    try:
        # Handle Money instances which support float() casting
        return float(value)
    except (TypeError, ValueError):
        pass

    value_str = str(value).strip()
    if not value_str:
        return 0.0

    # Remove any currency suffixes and thousands separators
    value_str = value_str.split(" ")[0].replace(",", "")

    try:
        return float(value_str)
    except ValueError:
        return 0.0


def compute_position_metrics(report: pd.DataFrame) -> dict[str, Any]:
    """Compute summary statistics from a positions report DataFrame."""
    if report.empty or "realized_pnl" not in report.columns:
        return {
            "total_count": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    pnl_series = report["realized_pnl"].map(parse_money_value)
    total_count = int(len(pnl_series))

    if total_count == 0:
        return {
            "total_count": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    winning = pnl_series[pnl_series > 0]
    losing = pnl_series[pnl_series < 0]

    win_rate = len(winning) / total_count if total_count else 0.0
    avg_win = winning.mean() if not winning.empty else 0.0
    avg_loss = losing.mean() if not losing.empty else 0.0

    return {
        "total_count": total_count,
        "win_rate": win_rate,
        "avg_win": float(avg_win) if avg_win else 0.0,
        "avg_loss": float(avg_loss) if avg_loss else 0.0,
    }


def compute_order_metrics(report: pd.DataFrame) -> dict[str, Any]:
    """Compute summary statistics from an orders report DataFrame."""
    if report.empty or "status" not in report.columns:
        return {
            "total_count": 0,
            "fill_rate": 0.0,
        }

    total_count = int(len(report))
    filled_count = int((report["status"] == "FILLED").sum())
    fill_rate = filled_count / total_count if total_count else 0.0

    return {
        "total_count": total_count,
        "fill_rate": fill_rate,
    }


def setup_backtest_engine(
    run_config: RunConfig,
    start_date: str,
    end_date: str,
    data_path: Path | None = None,
    catalog_path: Path | None = None,
) -> BacktestEngine | None:
    """
    Set up the backtest engine with dynamic configuration (Phase C).

    Parameters
    ----------
    run_config : RunConfig
        Run configuration with instrument and factor details.
    start_date : str
        Start date for the backtest (YYYY-MM-DD).
    end_date : str
        End date for the backtest (YYYY-MM-DD).
    data_path : Path, optional
        Path to the Feather data directory (fallback).
    catalog_path : Path, optional
        Path to the Parquet catalog (preferred).

    Returns
    -------
    BacktestEngine | None
        Configured backtest engine, or None if setup fails.
    """
    instrument_config = run_config.instrument

    # Create engine configuration with file logging
    config = BacktestEngineConfig(
        trader_id=f"BACKTESTER-{run_config.run_id}",
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="INFO",
            log_directory="./data/logs",
        ),
    )

    # Create backtest engine
    engine = BacktestEngine(config=config)

    # Get currencies
    # Note: base_currency (e.g., BTC) is for the instrument's underlying asset
    # account_currency (quote_currency, e.g., USDT) is for the account's base currency
    instrument_base_currency = get_currency_from_code(instrument_config.base_currency)
    quote_currency = get_currency_from_code(instrument_config.quote_currency)

    # Add venue with 2x leverage configuration
    venue = Venue(instrument_config.venue)

    # Create InstrumentId for leverage mapping
    instrument_id_str = f"{instrument_config.instrument_id}.{instrument_config.venue}"
    leverage_instrument_id = InstrumentId.from_str(instrument_id_str)

    from decimal import Decimal

    # Use USDT as account base currency (single-currency account)
    # For USDT-margined futures, only start with USDT balance
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=quote_currency,  # USDT as account base currency
        starting_balances=[
            Money(10_000, quote_currency),  # Only USDT for single-currency account
        ],
        default_leverage=Decimal("1.0"),  # Default 1x for other instruments
        leverages={
            leverage_instrument_id: Decimal("2.0"),  # 2x leverage for target instrument
        },
    )

    # Add instrument
    provider = TestInstrumentProvider()
    # Use provider method if available, otherwise create generic instrument
    instrument_method = f"{instrument_config.instrument_id.lower()}_binance"
    if hasattr(provider, instrument_method):
        instrument = getattr(provider, instrument_method)()
    else:
        # Create a generic instrument
        from nautilus_trader.model.instruments import CryptoFuture
        from nautilus_trader.model.objects import Price
        from nautilus_trader.model.objects import Quantity

        instrument_id = InstrumentId(
            symbol=Symbol(instrument_config.instrument_id),
            venue=venue,
        )
        instrument = CryptoFuture(
            id=instrument_id,
            raw_symbol=Symbol(instrument_config.instrument_id),
            underlying=instrument_base_currency,
            quote_currency=quote_currency,
            settlement_currency=quote_currency,
            is_inverse=False,
            activation_ns=0,
            expiration_ns=0,
            price_precision=2,  # Binance standard (data must match)
            size_precision=6,  # Binance standard
            price_increment=Price.from_str("0.01"),
            size_increment=Quantity.from_str("0.000001"),
            max_quantity=Quantity.from_str("1000000"),
            min_quantity=Quantity.from_str("0.000001"),
            max_price=Price.from_str("1000000"),
            min_price=Price.from_str("0.01"),
            ts_event=0,
            ts_init=0,
        )

    engine.add_instrument(instrument)

    # Load data based on data source preference
    bars = []
    instrument_id_str = f"{instrument_config.instrument_id}.{instrument_config.venue}"
    instrument_symbol = Symbol(instrument_config.instrument_id)
    instrument_venue = Venue(instrument_config.venue)
    instrument_id_obj = InstrumentId(symbol=instrument_symbol, venue=instrument_venue)

    # Try catalog first (Phase C preferred)
    if catalog_path and catalog_path.exists():
        try:
            catalog = create_catalog(catalog_path)
            # Load bars from catalog
            # Note: catalog.bars() returns a list of Bar objects, not a DataFrame
            bars_list = catalog.bars(
                instrument_ids=[instrument_id_str],
                start=pd.Timestamp(start_date),
                end=pd.Timestamp(end_date),
            )
            if bars_list:  # Check if list is not empty
                bars = bars_list if isinstance(bars_list, list) else list(bars_list)
                print(f"✅ Loaded {len(bars)} bars from catalog")
        except Exception as e:
            print(f"⚠️  Catalog load failed: {e}, falling back to Feather")

    # Fallback to Feather
    if not bars and data_path and data_path.exists():
        try:
            loader = FeatherBarLoader(data_path)

            # Check if extended bar support is available
            if loader._has_extended_bar:
                print("✅ Extended bar support detected - amt fields available")
            else:
                print("⚠️  Extended bar support not detected - OHLCV only")

            bars = loader.load_bars(
                instrument_id=instrument_id_obj,
                start_date=pd.Timestamp(start_date),
                end_date=pd.Timestamp(end_date),
            )

            if bars:
                print(f"✅ Loaded {len(bars)} bars from Feather")

                # Check first bar for extended fields
                if loader._has_extended_bar:
                    first_bar = bars[0]
                    amt = getattr(first_bar, "amt", None)
                    if amt is not None:
                        print(f"   First bar amt value: {amt:,.2f}")
        except Exception as e:
            print(f"❌ Feather load failed: {e}")

    if not bars:
        print(f"❌ No data loaded for {instrument_id_str} from {start_date} to {end_date}")
        return None

    # Add data to engine
    engine.add_data(bars)

    return engine


def run_single_backtest(
    run_config: RunConfig,
    config_loader: BacktestConfigLoader,
    start_date: str,
    end_date: str,
    data_path: Path | None,
    catalog_path: Path | None,
    output_dir: Path | None,
) -> dict[str, Any]:
    """
    Run a single backtest for an instrument×factor combination (Phase C).

    Parameters
    ----------
    run_config : RunConfig
        Run configuration.
    config_loader : BacktestConfigLoader
        Configuration loader with factor definitions.
    start_date : str
        Start date (YYYY-MM-DD).
    end_date : str
        End date (YYYY-MM-DD).
    data_path : Path | None
        Feather data path (fallback).
    catalog_path : Path | None
        Catalog data path (preferred).
    output_dir : Path | None
        Output directory for results.

    Returns
    -------
    dict[str, Any]
        Backtest results summary.
    """
    print("\n" + "=" * 80)
    print(f"Running: {run_config.run_id}")
    print(f"  Instrument: {run_config.instrument.instrument_id}.{run_config.instrument.venue}")
    print(f"  Factor: {run_config.factor.name}")
    print("=" * 80)

    try:
        # Set up backtest engine
        engine = setup_backtest_engine(
            run_config=run_config,
            start_date=start_date,
            end_date=end_date,
            data_path=data_path,
            catalog_path=catalog_path,
        )

        if not engine:
            return {
                "run_id": run_config.run_id,
                "status": "failed",
                "error": "Failed to set up engine",
            }

        # Create strategy configuration
        bar_type_str = (
            f"{run_config.instrument.instrument_id}.{run_config.instrument.venue}-"
            f"{run_config.instrument.bar_spec}"
        )

        strategy_cfg = SingleFactorStrategyConfig(
            instrument_id=f"{run_config.instrument.instrument_id}.{run_config.instrument.venue}",
            bar_type=bar_type_str,
            config_path=str(config_loader.config_path),
            factor_id=run_config.factor.factor_id,
            position_scale=run_config.position_scale,
            rebalance_interval=run_config.rebalance_interval,
        )

        # Add strategy to engine
        strategy = SingleFactorStrategy(config=strategy_cfg)
        engine.add_strategy(strategy)

        print(f"\n{'-' * 80}")
        print("Running backtest...")
        print(f"Period: {start_date} to {end_date}")
        print(f"Position Scale: {run_config.position_scale}")
        print(f"{'-' * 80}\n")

        # Run backtest
        engine.run()

        # Collect results
        venue = Venue(run_config.instrument.venue)
        account = engine.trader.generate_account_report(venue)
        positions_report = engine.trader.generate_positions_report()
        orders_report = engine.trader.generate_orders_report()

        position_stats = compute_position_metrics(positions_report)
        order_stats = compute_order_metrics(orders_report)

        # Get quote currency
        quote_currency = get_currency_from_code(run_config.instrument.quote_currency)

        # Calculate returns
        default_initial_value = 10_000.0
        initial_value = default_initial_value
        final_value = 0.0

        if not account.empty and {"currency", "total"}.issubset(account.columns):
            quote_code = str(quote_currency)
            quote_totals = account.loc[account["currency"] == quote_code, "total"].map(parse_money_value)

            if not quote_totals.empty:
                initial_value = quote_totals.iloc[0]
                final_value = quote_totals.iloc[-1]
        else:
            final_value = default_initial_value

        if initial_value == default_initial_value and final_value == 0.0:
            final_value = default_initial_value

        total_return = ((final_value - initial_value) / initial_value) * 100 if initial_value else 0

        # Calculate annualized return
        days = (datetime.fromisoformat(end_date) - datetime.fromisoformat(start_date)).days
        if days > 0:
            periods_per_year = 365 / days
            annualized_return = total_return * periods_per_year
        else:
            annualized_return = 0

        # Build results
        results = {
            "run_id": run_config.run_id,
            "status": "success",
            "instrument": run_config.instrument.instrument_id,
            "venue": run_config.instrument.venue,
            "factor": run_config.factor.name,
            "factor_id": run_config.factor.factor_id,
            "start_date": start_date,
            "end_date": end_date,
            "initial_balance": initial_value,
            "final_balance": final_value,
            "total_return_pct": round(total_return, 2),
            "annualized_return_pct": round(annualized_return, 2),
            "total_positions": position_stats["total_count"],
            "win_rate": round(position_stats["win_rate"] * 100, 2) if position_stats["win_rate"] else 0,
            "avg_win": position_stats["avg_win"],
            "avg_loss": position_stats["avg_loss"],
            "total_orders": order_stats["total_count"],
            "fill_rate": round(order_stats["fill_rate"] * 100, 2) if order_stats["fill_rate"] else 0,
        }

        # Print results
        print("\n" + "=" * 80)
        print("Backtest Results")
        print("=" * 80)
        print(f"Run ID: {results['run_id']}")
        print(f"Status: {results['status']}")
        print(f"\nPerformance:")
        print(f"  Total Return: {results['total_return_pct']:.2f}%")
        print(f"  Annualized Return: {results['annualized_return_pct']:.2f}%")
        print(f"  Final Balance: {results['final_balance']:,.2f} {run_config.instrument.quote_currency}")
        print(f"\nTrading Statistics:")
        print(f"  Total Positions: {results['total_positions']}")
        print(f"  Win Rate: {results['win_rate']:.2f}%")
        if results['avg_win'] > 0:
            print(f"  Avg Win: {results['avg_win']:,.2f} {run_config.instrument.quote_currency}")
        if results['avg_loss'] < 0:
            print(f"  Avg Loss: {results['avg_loss']:,.2f} {run_config.instrument.quote_currency}")
        print(f"  Total Orders: {results['total_orders']}")
        print(f"  Fill Rate: {results['fill_rate']:.2f}%")
        print("=" * 80)

        # Save results if output directory specified
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            result_file = output_dir / f"{run_config.run_id}_result.json"

            with open(result_file, "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n✅ Results saved to: {result_file}")

        # Dispose engine
        engine.dispose()

        return results

    except Exception as e:
        error_msg = f"Error running backtest: {e}"
        print(f"\n❌ {error_msg}")
        import traceback
        traceback.print_exc()

        return {
            "run_id": run_config.run_id,
            "status": "failed",
            "error": str(e),
        }


def run_batch_backtests(
    run_ids: list[str],
    config_loader: BacktestConfigLoader,
    start_date: str,
    end_date: str,
    data_path: Path | None,
    catalog_path: Path | None,
    output_dir: Path | None,
    max_workers: int = 1,
) -> list[dict[str, Any]]:
    """
    Run batch backtests for multiple instrument×factor combinations (Phase C).

    Parameters
    ----------
    run_ids : list[str]
        List of run IDs to execute.
    config_loader : BacktestConfigLoader
        Configuration loader.
    start_date : str
        Start date (YYYY-MM-DD).
    end_date : str
        End date (YYYY-MM-DD).
    data_path : Path | None
        Feather data path.
    catalog_path : Path | None
        Catalog data path.
    output_dir : Path | None
        Output directory for results.
    max_workers : int
        Maximum number of parallel workers.

    Returns
    -------
    list[dict[str, Any]]
        List of results for each run.
    """
    print("\n" + "=" * 80)
    print("BATCH BACKTEST EXECUTION (Phase C)")
    print("=" * 80)
    print(f"Total runs: {len(run_ids)}")
    print(f"Execution mode: {'Parallel' if max_workers > 1 else 'Sequential'}")
    if max_workers > 1:
        print(f"Max workers: {max_workers}")
    print("=" * 80)

    results = []

    if max_workers > 1:
        # Parallel execution
        print("\n⚡ Starting parallel execution...\n")

        # Note: ProcessPoolExecutor may have issues with complex objects
        # For now, we'll use sequential execution with a warning
        print("⚠️  Parallel execution not yet fully implemented - using sequential mode")
        max_workers = 1

    # Sequential execution
    for run_id in run_ids:
        try:
            run_config = config_loader.get_run(run_id)

            result = run_single_backtest(
                run_config=run_config,
                config_loader=config_loader,
                start_date=start_date,
                end_date=end_date,
                data_path=data_path,
                catalog_path=catalog_path,
                output_dir=output_dir,
            )

            results.append(result)

        except Exception as e:
            print(f"❌ Failed to execute run '{run_id}': {e}")
            results.append({
                "run_id": run_id,
                "status": "failed",
                "error": str(e),
            })

    # Print summary
    print("\n" + "=" * 80)
    print("BATCH BACKTEST SUMMARY")
    print("=" * 80)

    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful

    print(f"Total runs: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if successful > 0:
        print("\nSuccessful Runs:")
        for result in results:
            if result["status"] == "success":
                print(f"  {result['run_id']}: {result['total_return_pct']:.2f}% return")

    if failed > 0:
        print("\nFailed Runs:")
        for result in results:
            if result["status"] == "failed":
                print(f"  {result['run_id']}: {result.get('error', 'Unknown error')}")

    # Save summary
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_file = output_dir / "batch_summary.json"

        summary = {
            "total_runs": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"\n✅ Summary saved to: {summary_file}")

    print("=" * 80)

    return results


def _setup_data_directory():
    """Setup data and log directories for organized file storage."""
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)

    # Create logs directory for application logs
    logs_dir = Path("./data/logs")
    logs_dir.mkdir(exist_ok=True)

    print(f"📁 Data directory ready: {data_dir.absolute()}")
    print(f"📋 Logs directory ready: {logs_dir.absolute()}")


def main():
    """Main entry point for Phase C batch backtesting."""
    parser = argparse.ArgumentParser(
        description="Phase C: Multi-instrument×factor batch backtesting"
    )

    # Configuration
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path(__file__).parent / "configs" / "factors.yaml",
        help="Path to factor configuration YAML file",
    )

    # Execution mode (mutually exclusive)
    run_group = parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument(
        "--run-id",
        type=str,
        help="Execute a single run by ID (e.g., 'btc_amt_momentum')",
    )
    run_group.add_argument(
        "--run-ids",
        type=str,
        help="Execute multiple runs (comma-separated, e.g., 'btc_amt_momentum,eth_amt_momentum')",
    )
    run_group.add_argument(
        "--all-runs",
        action="store_true",
        help="Execute all enabled runs from configuration",
    )
    run_group.add_argument(
        "--list-runs",
        action="store_true",
        help="List all available runs and exit",
    )

    # Data sources
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Path to Feather data directory (fallback)",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=Path(__file__).parent / "catalog",
        help="Path to Parquet catalog (preferred)",
    )

    # Backtest parameters
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

    # Execution control
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1 = sequential)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Output directory for results (default: ./results)",
    )

    args = parser.parse_args()

    # Setup data and log directories
    _setup_data_directory()

    # Validate config file
    if not args.config_path.exists():
        print(f"❌ Configuration file not found: {args.config_path}")
        return 1

    # Load configuration
    try:
        config_loader = BacktestConfigLoader(args.config_path)
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return 1

    # List runs if requested
    if args.list_runs:
        print("\n" + "=" * 80)
        print("AVAILABLE RUNS (Phase C)")
        print("=" * 80)

        enabled_runs = config_loader.list_runs(enabled_only=True)
        disabled_runs = [r for r in config_loader.list_runs(enabled_only=False) if r not in enabled_runs]

        print(f"\nEnabled Runs ({len(enabled_runs)}):")
        for run_id in enabled_runs:
            run = config_loader.get_run(run_id)
            print(f"  {run_id}:")
            print(f"    Instrument: {run.instrument.instrument_id}.{run.instrument.venue}")
            print(f"    Factor: {run.factor.name}")
            print(f"    Position Scale: {run.position_scale}")

        if disabled_runs:
            print(f"\nDisabled Runs ({len(disabled_runs)}):")
            for run_id in disabled_runs:
                run = config_loader.get_run(run_id)
                print(f"  {run_id}:")
                print(f"    Instrument: {run.instrument.instrument_id}.{run.instrument.venue}")
                print(f"    Factor: {run.factor.name}")
                print(f"    Status: DISABLED")

        print("\n" + "=" * 80)
        print(f"\nUsage:")
        print(f"  Single run:    python run_backtest.py --run-id btc_amt_momentum")
        print(f"  Multiple runs: python run_backtest.py --run-ids btc_amt_momentum,eth_amt_momentum")
        print(f"  All runs:      python run_backtest.py --all-runs")
        print(f"  Parallel:      python run_backtest.py --all-runs --max-workers 4")
        print("=" * 80)

        return 0

    # Determine which runs to execute
    run_ids_to_execute = []

    if args.run_id:
        # Single run
        run_ids_to_execute = [args.run_id]
    elif args.run_ids:
        # Multiple runs (comma-separated)
        run_ids_to_execute = [r.strip() for r in args.run_ids.split(",")]
    elif args.all_runs:
        # All enabled runs
        run_ids_to_execute = config_loader.list_runs(enabled_only=True)

    if not run_ids_to_execute:
        print("❌ No runs specified. Use --run-id, --run-ids, --all-runs, or --list-runs")
        return 1

    # Validate all run IDs
    for run_id in run_ids_to_execute:
        try:
            config_loader.get_run(run_id)
        except KeyError:
            print(f"❌ Run '{run_id}' not found in configuration")
            print(f"Available runs: {', '.join(config_loader.list_runs(enabled_only=False))}")
            return 1

    # Display configuration summary
    print("\n" + "=" * 80)
    print("PHASE C BACKTEST CONFIGURATION")
    print("=" * 80)
    print(f"Config File: {args.config_path}")
    print(f"Runs to Execute: {len(run_ids_to_execute)}")
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Data Sources: Catalog (preferred), Feather (fallback)")
    print(f"Execution Mode: {'Parallel' if args.max_workers > 1 else 'Sequential'}")
    if args.max_workers > 1:
        print(f"Max Workers: {args.max_workers}")
    print(f"Output Directory: {args.output_dir}")
    print("=" * 80)

    # Execute backtests
    results = run_batch_backtests(
        run_ids=run_ids_to_execute,
        config_loader=config_loader,
        start_date=args.start_date,
        end_date=args.end_date,
        data_path=args.data_path if args.data_path.exists() else None,
        catalog_path=args.catalog_path if args.catalog_path.exists() else None,
        output_dir=args.output_dir,
        max_workers=args.max_workers,
    )

    # Determine success
    failed = sum(1 for r in results if r["status"] == "failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
