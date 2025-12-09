#!/usr/bin/env python3
"""Convenience launcher for running Aurora HDG in a live trading node."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.adapters.binance import BinanceLiveExecClientFactory
from nautilus_trader.adapters.okx import OKXLiveDataClientFactory
from nautilus_trader.adapters.okx import OKXLiveExecClientFactory
from nautilus_trader.live.node import TradingNode

from Aurora_Lattice.aurora_hdg import AuroraHdgStrategy
from Aurora_Lattice.config_loader import (
    AuroraRuntimeProfile,
    apply_runtime_overrides,
    build_trading_node_config,
    load_run_bundle,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "configs" / "default.yaml"
DEFAULT_ENV_PATH = Path(os.getenv("AURORA_ENV_FILE", PACKAGE_ROOT / ".env"))

FACTORY_REGISTRY = {
    "BINANCE": (BinanceLiveDataClientFactory, BinanceLiveExecClientFactory),
    "OKX": (OKXLiveDataClientFactory, OKXLiveExecClientFactory),
}


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
    parser.add_argument("--trader-id", default=None, help="Override trader_id from the config file.")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override log level from the config file.",
    )
    parser.add_argument(
        "--log-level-file",
        default=None,
        help="Override file log level from the config file.",
    )
    parser.add_argument(
        "--log-file-name",
        default=None,
        help="Override log file name from the config file.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Override log directory from the config file.",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=None,
        help="Override catalog path from the config file.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Path to .env containing BINANCE credentials (auto-loaded if present).",
    )
    parser.add_argument(
        "--futures-leverage",
        default=os.getenv("AURORA_FUTURES_LEVERAGE"),
        help="Optional uniform leverage override (used when client config omits one).",
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


def run_preflight(config_path: Path, runtime_profile: AuroraRuntimeProfile) -> None:
    errors: list[str] = []
    if sys.version_info < (3, 9):
        errors.append("Python 3.9+ is required.")
    if not config_path.exists():
        errors.append(f"Strategy config not found: {config_path}")
    for env_var in runtime_profile.missing_envs():
        errors.append(f"Missing environment variable: {env_var}")
    if errors:
        for line in errors:
            print(f"❌ {line}")
        raise SystemExit(1)


def main() -> None:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    load_env_file(args.env_file)
    if not config_path.exists():
        print(f"❌ Strategy config not found: {config_path}")
        raise SystemExit(1)

    strategy_config, runtime_profile = load_run_bundle(config_path)
    runtime_profile = apply_runtime_overrides(
        runtime_profile,
        trader_id=args.trader_id,
        log_level=args.log_level,
        log_level_file=args.log_level_file,
        log_file_name=args.log_file_name,
        log_directory=args.log_dir,
        catalog_path=args.catalog_path,
        futures_leverage=args.futures_leverage,
    )

    run_preflight(config_path, runtime_profile)

    node_config = build_trading_node_config(runtime_profile)

    node = TradingNode(config=node_config)
    registered_data_factories: set[str] = set()
    registered_exec_factories: set[str] = set()
    for client in runtime_profile.clients:
        factories = FACTORY_REGISTRY.get(client.venue)
        if factories is None:
            continue
        data_factory, exec_factory = factories
        factory_key = client.key.split("-", 1)[0]
        if client.use_data_client and factory_key not in registered_data_factories:
            node.add_data_client_factory(factory_key, data_factory)
            registered_data_factories.add(factory_key)
        if client.use_exec_client and factory_key not in registered_exec_factories:
            node.add_exec_client_factory(factory_key, exec_factory)
            registered_exec_factories.add(factory_key)

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
