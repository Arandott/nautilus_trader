"""Helpers for building a TradingNodeConfig suitable for Aurora HDG live trading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceDataClientConfig
from nautilus_trader.adapters.binance import BinanceExecClientConfig
from nautilus_trader.adapters.binance.common.symbol import BinanceSymbol
from nautilus_trader.config import CacheConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.config import LiveDataEngineConfig
from nautilus_trader.live.config import LiveRiskEngineConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.persistence.config import DataCatalogConfig
from nautilus_trader.persistence.config import StreamingConfig


@dataclass(frozen=True)
class AuroraRuntimeSettings:
    """
    Container for runtime settings needed to assemble a live TradingNode.

    Parameters
    ----------
    api_key : str
        Binance API key.
    api_secret : str
        Binance API secret.
    trader_id : str
        Trader identifier handed to `TradingNodeConfig`.
    testnet : bool
        If the Binance clients should target the testnet endpoints.
    log_level : str
        Minimum log level for stdout/file logging.
    log_directory : Path
        Directory for structured logs.
    catalog_path : Path
        Directory storing parquet catalog + streaming output.
    instrument_ids : frozenset[InstrumentId]
        Instruments to load via the InstrumentProvider.
    futures_leverage : int | None
        Optional leverage override applied uniformly across configured instruments.
    """

    api_key: str
    api_secret: str
    trader_id: str
    testnet: bool
    log_level: str
    log_directory: Path
    catalog_path: Path
    instrument_ids: frozenset[InstrumentId]
    futures_leverage: int | None = None

    def ensure_directories(self) -> None:
        """Create directories used for logs and catalog if they do not exist."""
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.catalog_path.mkdir(parents=True, exist_ok=True)


def _build_leverage_map(
    instrument_ids: Iterable[InstrumentId],
    leverage: int | None,
) -> dict[BinanceSymbol, int] | None:
    if leverage is None:
        return None
    if leverage <= 0:
        raise ValueError("`futures_leverage` must be positive when supplied.")
    return {BinanceSymbol(inst.symbol): leverage for inst in instrument_ids}


def build_trading_node_config(settings: AuroraRuntimeSettings) -> TradingNodeConfig:
    """
    Return a fully wired `TradingNodeConfig` for live Aurora trading.
    """

    settings.ensure_directories()
    leverage_map = _build_leverage_map(settings.instrument_ids, settings.futures_leverage)

    provider_config = InstrumentProviderConfig(
        load_all=False,
        load_ids=settings.instrument_ids,
    )

    return TradingNodeConfig(
        trader_id=TraderId(settings.trader_id),
        logging=LoggingConfig(
            log_level=settings.log_level,
            log_directory=str(settings.log_directory),
            log_file_format="json",
            log_colors=True,
        ),
        data_engine=LiveDataEngineConfig(graceful_shutdown_on_exception=True),
        exec_engine=LiveExecEngineConfig(
            graceful_shutdown_on_exception=True,
            reconciliation=True,
            reconciliation_lookback_mins=1_440,
            snapshot_orders=True,
            snapshot_positions=True,
            snapshot_positions_interval_secs=5.0,
        ),
        risk_engine=LiveRiskEngineConfig(
            graceful_shutdown_on_exception=True,
            bypass=False,
            max_order_submit_rate="40/00:00:01",
            max_order_modify_rate="20/00:00:01",
        ),
        cache=CacheConfig(
            timestamps_as_iso8601=True,
            flush_on_start=False,
        ),
        catalogs=[
            DataCatalogConfig(
                path=str(settings.catalog_path),
                name="aurora_catalog",
            ),
        ],
        streaming=StreamingConfig(
            catalog_path=str(settings.catalog_path),
            flush_interval_ms=30_000,
            replace_existing=True,
        ),
        data_clients={
            BINANCE: BinanceDataClientConfig(
                api_key=settings.api_key,
                api_secret=settings.api_secret,
                account_type=BinanceAccountType.USDT_FUTURES,
                testnet=settings.testnet,
                instrument_provider=provider_config,
                update_instruments_interval_mins=60,
            ),
        },
        exec_clients={
            BINANCE: BinanceExecClientConfig(
                api_key=settings.api_key,
                api_secret=settings.api_secret,
                account_type=BinanceAccountType.USDT_FUTURES,
                testnet=settings.testnet,
                futures_leverages=leverage_map,
                instrument_provider=provider_config,
                max_retries=3,
                retry_delay_initial_ms=1_000,
                retry_delay_max_ms=10_000,
                use_position_ids=True,
                use_reduce_only=False,
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=15.0,
        timeout_portfolio=15.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )
