#!/usr/bin/env python3
"""数据专用的在线学习脚本：只订阅行情，实时训练 RLS Alpha，不下单。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from dataclasses import replace

from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import BookType
from nautilus_trader.trading.strategy import Strategy

from Aurora_Lattice.aurora_hdg.config import AuroraHDGConfig
from Aurora_Lattice.config_loader import (
    AuroraRuntimeProfile,
    apply_runtime_overrides,
    build_trading_node_config,
    load_run_bundle,
)


# 复用 run_live_trading 的 env 加载逻辑，避免遗漏密钥。
def load_env_file(env_path: Path) -> None:
    env_path = env_path.expanduser().resolve()
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
        return
    except ImportError:
        pass

    with env_path.open() as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ[key.strip()] = value.strip()


class AlphaLiveLearner(Strategy):
    """仅做在线学习的“伪策略”，无下单逻辑。"""

    def __init__(self, config: AuroraHDGConfig, log_every: int = 200) -> None:
        super().__init__(config)
        self.instrument = None
        self._book_type = BookType.L2_MBP
        self._alpha_engine: aurora_bindings.AlphaEngine | None = None
        self._tick_size: float = float(self.config.tick_size)
        self._log_every = max(log_every, 1)
        self._updates = 0
        self._pyo3_instrument_id = nautilus_pyo3.InstrumentId.from_str(self.config.instrument_id.value)
        self._pyo3_book_type = nautilus_pyo3.BookType(self._book_type.name)

    # --- lifecycle ---

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            raise RuntimeError(f"Instrument {self.config.instrument_id} missing")

        self._tick_size = self.instrument.price_increment.as_double()
        features = ["imbalance", "micro_skew", "sigma_rel"]
        rls_model = aurora_bindings.RlsAlpha(
            dimension=len(features),
            params=aurora_bindings.RlsParams(
                forgetting=self.config.alpha.rls_forgetting,
                ridge=1.0,
                a_max_bps=self.config.alpha.a_max_bps,
            ),
        )
        alpha_params = aurora_bindings.AlphaEngineParams(
            lag_ns=int(self.config.alpha.tau_ms * 1e6),
            tick_size=self._tick_size,
            i_max=self.config.inventory.i_max,
            time_stride_ns=0,
            count_stride=1,
            min_updates_for_output=0,
            label_queue_len=4096,
            base_sigma=1e-6,
            features=features,
        )
        self._alpha_engine = aurora_bindings.AlphaEngine(
            model=rls_model,
            instrument_id=self._pyo3_instrument_id,
            book_type=self._pyo3_book_type,
            params=alpha_params,
        )

        # 仅订阅行情（订单簿 + 成交），不注册执行客户端。
        self.subscribe_order_book_deltas(
            self.config.instrument_id,
            self._book_type,
            managed=False,
            pyo3_conversion=True,
        )
        self.log.info(
            f"AlphaLiveLearner started for {self.config.instrument_id} (data-only)",
            LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.log.info("AlphaLiveLearner stopped", LogColor.YELLOW)

    # --- data handlers ---

    def on_order_book_deltas(self, deltas: nautilus_pyo3.OrderBookDeltas) -> None:
        if deltas.instrument_id.value != self.config.instrument_id.value:
            return

        pred_bps = self._alpha_engine.handle_order_book(deltas.ts_event, deltas, 0.0)

        self._updates += 1
        if self._updates % self._log_every == 0:
            self.log.info(
                f"[alpha] updates={self._updates} last_pred={pred_bps:.4f}bps",
                LogColor.YELLOW,
            )


def _disable_exec_clients(profile: AuroraRuntimeProfile) -> AuroraRuntimeProfile:
    clients = tuple(replace(client, use_exec_client=False) for client in profile.clients)
    return replace(profile, clients=clients)


def _register_data_factories(node: TradingNode, profile: AuroraRuntimeProfile) -> None:
    # 延用 run_live_trading 中的去重逻辑。
    from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
    from nautilus_trader.adapters.okx import OKXLiveDataClientFactory

    registry = {
        "BINANCE": BinanceLiveDataClientFactory,
        "OKX": OKXLiveDataClientFactory,
    }

    registered: set[str] = set()
    for client in profile.clients:
        if not client.use_data_client:
            continue
        factory = registry.get(client.venue)
        if factory is None:
            continue
        factory_key = client.key.split("-", 1)[0]
        if factory_key in registered:
            continue
        node.add_data_client_factory(factory_key, factory)
        registered.add(factory_key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Data-only online learner for Aurora RLS alpha.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "configs" / "default.yaml",
        help="Path to Aurora config (含 strategy + runtime).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.getenv("AURORA_ENV_FILE", Path(__file__).resolve().parents[2] / ".env")),
        help="Path to .env containing venue credentials.",
    )
    parser.add_argument(
        "--trader-id",
        default=None,
        help="Override trader_id from config.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override log level.",
    )
    parser.add_argument(
        "--log-level-file",
        default=None,
        help="Override file log level.",
    )
    parser.add_argument(
        "--log-file-name",
        default=None,
        help="Override log file name.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Override log directory.",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=None,
        help="Override catalog path.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=200,
        help="Log alpha rolling correlation every N updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    if not config_path.exists():
        raise SystemExit(f"❌ Config not found: {config_path}")

    load_env_file(args.env_file)
    strategy_cfg, runtime_profile = load_run_bundle(config_path)
    runtime_profile = apply_runtime_overrides(
        runtime_profile,
        trader_id=args.trader_id,
        log_level=args.log_level,
        log_level_file=args.log_level_file,
        log_file_name=args.log_file_name,
        log_directory=args.log_dir,
        catalog_path=args.catalog_path,
        futures_leverage=None,  # 数据模式不需要
    )
    runtime_profile = _disable_exec_clients(runtime_profile)
    runtime_profile.ensure_directories()

    node_config = build_trading_node_config(runtime_profile)
    node = TradingNode(config=node_config)
    _register_data_factories(node, runtime_profile)

    learner = AlphaLiveLearner(strategy_cfg, log_every=args.log_every)
    node.trader.add_strategy(learner)

    try:
        node.build()
        print("✅ AlphaLiveLearner node built. Press Ctrl+C to stop.")
        node.run()
    except KeyboardInterrupt:
        print("🛑 Shutdown requested by user.")
    finally:
        node.dispose()


if __name__ == "__main__":
    main()
