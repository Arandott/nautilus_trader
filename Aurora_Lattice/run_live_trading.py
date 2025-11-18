#!/usr/bin/env python3
"""Convenience launcher for running Aurora HDG in a live trading node."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId

from Aurora_Lattice.aurora_hdg import AuroraHdgStrategy, load_config
from Aurora_Lattice.live_trading_config import AuroraRuntimeSettings, build_trading_node_config

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "configs" / "default.yaml"
DEFAULT_ENV_PATH = Path(os.getenv("AURORA_ENV_FILE", PACKAGE_ROOT / ".env"))
REQUIRED_ENV = ("BINANCE_API_KEY", "BINANCE_API_SECRET")


def _resolve_trading_mode() -> bool:
    return os.getenv("AURORA_TRADING_MODE", "testnet").lower() != "live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Aurora HDG strategy through a TradingNode for live execution.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to Aurora HDG strategy config (YAML/JSON).",
    )
    parser.add_argument(
        "--trader-id",
        default=os.getenv("AURORA_TRADER_ID", "AURORA-HDG-LIVE"),
        help="Trader ID supplied to TradingNodeConfig (default: %(default)s).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("AURORA_LOG_LEVEL", "INFO"),
        help="Root log level for the TradingNode (default: %(default)s).",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(os.getenv("AURORA_LOG_DIR", PACKAGE_ROOT / "data" / "logs")),
        help="Directory for structured logs (created if missing).",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=Path(os.getenv("AURORA_CATALOG_PATH", PACKAGE_ROOT / "data" / "catalog")),
        help="Directory used for parquet catalog + streaming output.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Path to .env containing BINANCE credentials (auto-loaded if present).",
    )
    parser.add_argument(
        "--futures-leverage",
        type=int,
        default=os.getenv("AURORA_FUTURES_LEVERAGE"),
        help="Optional uniform leverage override for Binance futures positions.",
    )

    return parser.parse_args()


def load_env_file(env_path: Path) -> None:
    if not env_path:
        return

    env_path = env_path.expanduser().resolve()
    if not env_path.exists():
        print(f"ℹ️  No .env file at {env_path}, falling back to existing environment.")
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
        print(f"✅ Environment loaded from {env_path}")
        return
    except ImportError:
        print("⚠️  python-dotenv not installed; performing manual .env parsing...")

    with env_path.open() as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ[key.strip()] = value.strip()
    print(f"✅ Environment loaded via manual parsing from {env_path}")


def run_preflight(config_path: Path) -> None:
    errors: list[str] = []
    if sys.version_info < (3, 9):
        errors.append("Python 3.9+ is required.")
    if not config_path.exists():
        errors.append(f"Strategy config not found: {config_path}")
    for env_var in REQUIRED_ENV:
        if not os.getenv(env_var):
            errors.append(f"Missing environment variable: {env_var}")
    if errors:
        for line in errors:
            print(f"❌ {line}")
        raise SystemExit(1)


def build_runtime_settings(
    args: argparse.Namespace,
    instrument_id: InstrumentId,
) -> AuroraRuntimeSettings:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    leverage = None
    if args.futures_leverage not in (None, ""):
        leverage = int(args.futures_leverage)
    return AuroraRuntimeSettings(
        api_key=api_key,
        api_secret=api_secret,
        trader_id=args.trader_id,
        testnet=_resolve_trading_mode(),
        log_level=args.log_level,
        log_directory=Path(args.log_dir).expanduser().resolve(),
        catalog_path=Path(args.catalog_path).expanduser().resolve(),
        instrument_ids=frozenset({instrument_id}),
        futures_leverage=leverage,
    )


def main() -> None:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    load_env_file(args.env_file)
    run_preflight(config_path)

    strategy_config = load_config(config_path)
    runtime_settings = build_runtime_settings(args, strategy_config.instrument_id)
    node_config = build_trading_node_config(runtime_settings)

    node = TradingNode(config=node_config)
    node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
    node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)

    strategy = AuroraHdgStrategy(strategy_config)
    node.trader.add_strategy(strategy)

    try:
        node.build()
        print("✅ Aurora HDG trading node built. Press Ctrl+C to stop.")
        node.run()
    except KeyboardInterrupt:
        print("🛑 Shutdown requested by user.")
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
