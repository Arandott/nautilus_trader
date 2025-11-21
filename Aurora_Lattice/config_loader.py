"""Centralized loader for Aurora strategy + runtime configuration bundles."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceDataClientConfig
from nautilus_trader.adapters.binance import BinanceExecClientConfig
from nautilus_trader.adapters.binance.common.symbol import BinanceSymbol
from nautilus_trader.adapters.okx import OKXDataClientConfig
from nautilus_trader.adapters.okx import OKXExecClientConfig
from nautilus_trader.config import CacheConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.core.nautilus_pyo3 import OKXContractType
from nautilus_trader.core.nautilus_pyo3 import OKXInstrumentType
from nautilus_trader.core.nautilus_pyo3 import OKXMarginMode
from nautilus_trader.core.nautilus_pyo3 import OKXVipLevel
from nautilus_trader.live.config import LiveDataEngineConfig
from nautilus_trader.live.config import LiveRiskEngineConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.persistence.config import DataCatalogConfig
from nautilus_trader.persistence.config import StreamingConfig

from Aurora_Lattice.aurora_hdg.config import (
    AuroraHDGConfig,
    build_strategy_config,
    read_config_data,
)

VENUE_CREDENTIAL_DEFAULTS = {
    "BINANCE": {
        "api_key": "BINANCE_API_KEY",
        "api_secret": "BINANCE_API_SECRET",
    },
    "OKX": {
        "api_key": "OKX_API_KEY",
        "api_secret": "OKX_API_SECRET",
        "api_passphrase": "OKX_API_PASSPHRASE",
    },
}


def _resolve_account_type(raw: str | None) -> BinanceAccountType:
    source = (raw or BinanceAccountType.SPOT.name).upper()
    try:
        return BinanceAccountType[source]
    except KeyError:
        raise ValueError(
            f"Unsupported Binance account type `{raw}`. "
            "Expected one of {SPOT, MARGIN, USDT_FUTURES, COIN_FUTURES}.",
        ) from None


def _resolve_path(value: str | None, config_dir: Path, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (config_dir / path).resolve()
    return path


def _parse_instrument_ids(raw_ids: list[str], default: InstrumentId) -> frozenset[InstrumentId]:
    ids = {default}
    for raw in raw_ids:
        ids.add(InstrumentId.from_str(raw))
    return frozenset(ids)


@dataclass(frozen=True)
class CredentialRef:
    """Tracks environment variables that hold venue credential secrets."""

    env_map: dict[str, str]

    def required_envs(self) -> set[str]:
        return {env for env in self.env_map.values() if env}

    def missing_envs(self) -> list[str]:
        return [env for env in self.required_envs() if env not in os.environ]

    def has(self, field: str) -> bool:
        return field in self.env_map

    def resolve(self, field: str) -> str:
        env = self.env_map.get(field)
        if not env:
            raise RuntimeError(f"Credential field `{field}` is not configured.")
        value = os.environ.get(env)
        if value is None:
            raise RuntimeError(f"Missing environment variable: {env}")
        return value

    def resolve_many(self, required: Sequence[str]) -> dict[str, str]:
        return {field: self.resolve(field) for field in required}


@dataclass(frozen=True)
class AuroraVenueClient:
    """Runtime wiring for a single venue account entry."""

    key: str
    venue: str
    testnet: bool
    instrument_ids: frozenset[InstrumentId]
    update_instruments_interval_mins: int | None
    use_data_client: bool
    use_exec_client: bool
    credentials: CredentialRef
    params: Mapping[str, Any]


@dataclass(frozen=True)
class AuroraRuntimeProfile:
    """Parsed runtime configuration tied to a single strategy run."""

    trader_id: str
    log_level: str
    log_directory: Path
    catalog_path: Path
    trading_mode: str
    clients: tuple[AuroraVenueClient, ...]

    def ensure_directories(self) -> None:
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.catalog_path.mkdir(parents=True, exist_ok=True)

    def missing_envs(self) -> list[str]:
        missing: set[str] = set()
        for client in self.clients:
            if not (client.use_data_client or client.use_exec_client):
                continue
            missing.update(client.credentials.missing_envs())
        return sorted(missing)


def _build_credential_ref(
    client_key: str,
    venue: str,
    cred_data: Mapping[str, Any] | None,
) -> CredentialRef:
    defaults = VENUE_CREDENTIAL_DEFAULTS.get(venue.upper())
    if defaults is None:
        raise ValueError(f"Client `{client_key}` references unsupported venue `{venue}`.")

    env_map = dict(defaults)
    if cred_data:
        for field, env_name in cred_data.items():
            if env_name in ("", None):
                continue
            if field.endswith("_env"):
                normalized = field[: -len("_env")]
            else:
                raise ValueError(
                    f"Client `{client_key}` supplied inline credential `{field}`. "
                    "Please store secrets in environment variables (e.g. MY_KEY_env).",
                )
            env_map[normalized] = str(env_name)

    return CredentialRef(env_map)


def build_runtime_profile(
    runtime_data: Mapping[str, Any],
    config_dir: Path,
    default_instrument: InstrumentId,
) -> AuroraRuntimeProfile:
    trader_id = runtime_data.get("trader_id") or os.getenv("AURORA_TRADER_ID", "AURORA-HDG-LIVE")
    log_level = runtime_data.get("log_level") or os.getenv("AURORA_LOG_LEVEL", "INFO")
    trading_mode = runtime_data.get("trading_mode", "testnet")
    log_dir = _resolve_path(
        runtime_data.get("log_directory"),
        config_dir,
        default=config_dir.parent / "data" / "logs",
    )
    catalog_path = _resolve_path(
        runtime_data.get("catalog_path"),
        config_dir,
        default=config_dir.parent / "data" / "catalog",
    )

    clients_raw = runtime_data.get("clients")
    if not clients_raw:
        raise ValueError("`runtime.clients` must contain at least one venue definition.")

    default_testnet = trading_mode.lower() != "live"
    reserved = {
        "venue",
        "credentials",
        "instrument_ids",
        "use_data_client",
        "use_exec_client",
        "update_instruments_interval_mins",
        "testnet",
    }

    clients: list[AuroraVenueClient] = []
    for key, client_data in clients_raw.items():
        venue = (client_data.get("venue") or "BINANCE").upper()
        builder = VENUE_BUILDERS.get(venue)
        if builder is None:
            raise ValueError(f"Unsupported venue `{venue}` for client `{key}`.")

        client_testnet = client_data.get("testnet")
        if client_testnet is None:
            client_testnet = default_testnet

        instrument_ids_raw = client_data.get("instrument_ids") or []
        instrument_ids = _parse_instrument_ids(instrument_ids_raw, default_instrument)
        use_data = client_data.get("use_data_client", True)
        use_exec = client_data.get("use_exec_client", True)
        if not use_data and not use_exec:
            raise ValueError(f"Client `{key}` must enable at least one of data/exec clients.")

        credentials = _build_credential_ref(key, venue, client_data.get("credentials"))
        params = {k: v for k, v in client_data.items() if k not in reserved}

        clients.append(
            AuroraVenueClient(
                key=key,
                venue=venue,
                testnet=bool(client_testnet),
                instrument_ids=instrument_ids,
                update_instruments_interval_mins=client_data.get("update_instruments_interval_mins", 60),
                use_data_client=use_data,
                use_exec_client=use_exec,
                credentials=credentials,
                params=params,
            ),
        )

    return AuroraRuntimeProfile(
        trader_id=trader_id,
        log_level=log_level,
        log_directory=log_dir.expanduser().resolve(),
        catalog_path=catalog_path.expanduser().resolve(),
        trading_mode=trading_mode,
        clients=tuple(clients),
    )


def apply_runtime_overrides(
    profile: AuroraRuntimeProfile,
    *,
    trader_id: str | None = None,
    log_level: str | None = None,
    log_directory: Path | None = None,
    catalog_path: Path | None = None,
    futures_leverage: int | None = None,
) -> AuroraRuntimeProfile:
    updates: dict[str, Any] = {}
    if trader_id:
        updates["trader_id"] = trader_id
    if log_level:
        updates["log_level"] = log_level
    if log_directory:
        updates["log_directory"] = log_directory.expanduser().resolve()
    if catalog_path:
        updates["catalog_path"] = catalog_path.expanduser().resolve()

    updated = profile
    if updates:
        updated = replace(updated, **updates)

    if futures_leverage not in (None, ""):
        value = int(futures_leverage)
        new_clients = []
        for client in updated.clients:
            if client.venue == "BINANCE" and "futures_leverage" not in client.params:
                params = dict(client.params)
                params["futures_leverage"] = value
                new_clients.append(replace(client, params=params))
            else:
                new_clients.append(client)
        updated = replace(updated, clients=tuple(new_clients))

    return updated


def _build_leverage_map(
    instrument_ids: frozenset[InstrumentId],
    leverage: int | None,
) -> dict[BinanceSymbol, int] | None:
    if leverage is None:
        return None
    if leverage <= 0:
        raise ValueError("`futures_leverage` must be positive when supplied.")
    return {
        BinanceSymbol(instrument.symbol.value): leverage
        for instrument in instrument_ids
    }


def _build_binance_client_configs(client: AuroraVenueClient, provider: InstrumentProviderConfig):
    creds = client.credentials.resolve_many(["api_key", "api_secret"])
    params = dict(client.params)

    account_type = _resolve_account_type(params.pop("account_type", None))
    futures_leverage = params.pop("futures_leverage", None)
    use_position_ids = params.pop("use_position_ids", True)
    use_reduce_only = params.pop("use_reduce_only", False)
    max_retries = params.pop("max_retries", 3)
    retry_delay_initial_ms = params.pop("retry_delay_initial_ms", 1_000)
    retry_delay_max_ms = params.pop("retry_delay_max_ms", 10_000)
    use_trade_lite = params.pop("use_trade_lite", False)
    treat_expired_as_canceled = params.pop("treat_expired_as_canceled", False)
    use_agg_trade_ticks = params.pop("use_agg_trade_ticks", False)
    key_type = params.pop("key_type", None)
    base_url_http = params.pop("base_url_http", None)
    base_url_ws = params.pop("base_url_ws", None)
    us = params.pop("us", False)

    data_config = None
    if client.use_data_client:
        data_kwargs = dict(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            account_type=account_type,
            testnet=client.testnet,
            instrument_provider=provider,
            update_instruments_interval_mins=client.update_instruments_interval_mins,
            use_agg_trade_ticks=use_agg_trade_ticks,
            us=us,
        )
        if key_type:
            data_kwargs["key_type"] = key_type
        if base_url_http:
            data_kwargs["base_url_http"] = base_url_http
        if base_url_ws:
            data_kwargs["base_url_ws"] = base_url_ws
        data_config = BinanceDataClientConfig(**data_kwargs)

    exec_config = None
    if client.use_exec_client:
        exec_kwargs = dict(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            account_type=account_type,
            testnet=client.testnet,
            instrument_provider=provider,
            futures_leverages=_build_leverage_map(client.instrument_ids, futures_leverage),
            max_retries=max_retries,
            retry_delay_initial_ms=retry_delay_initial_ms,
            retry_delay_max_ms=retry_delay_max_ms,
            use_position_ids=use_position_ids,
            use_reduce_only=use_reduce_only,
            use_trade_lite=use_trade_lite,
            treat_expired_as_canceled=treat_expired_as_canceled,
            us=us,
        )
        if key_type:
            exec_kwargs["key_type"] = key_type
        if base_url_http:
            exec_kwargs["base_url_http"] = base_url_http
        if base_url_ws:
            exec_kwargs["base_url_ws"] = base_url_ws
        exec_config = BinanceExecClientConfig(**exec_kwargs)

    return data_config, exec_config


def _parse_okx_sequence(values, enum_cls):
    if values is None:
        return None
    parsed = []
    for value in values:
        if isinstance(value, enum_cls):
            parsed.append(value)
        else:
            parsed.append(enum_cls[value.upper()])
    return tuple(parsed)


def _parse_okx_enum(value, enum_cls):
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    return enum_cls[value.upper()]


def _build_okx_client_configs(client: AuroraVenueClient, provider: InstrumentProviderConfig):
    creds = client.credentials.resolve_many(["api_key", "api_secret", "api_passphrase"])
    params = dict(client.params)

    instrument_types = _parse_okx_sequence(params.pop("instrument_types", None), OKXInstrumentType)
    contract_types = _parse_okx_sequence(params.pop("contract_types", None), OKXContractType)
    instrument_families = params.pop("instrument_families", None)
    margin_mode = _parse_okx_enum(params.pop("margin_mode", None), OKXMarginMode)
    vip_level = _parse_okx_enum(params.pop("vip_level", None), OKXVipLevel)
    is_demo = params.pop("is_demo", client.testnet)

    base_url_http = params.pop("base_url_http", None)
    base_url_ws = params.pop("base_url_ws", None)
    use_spot_margin = params.pop("use_spot_margin", False)
    max_retries = params.pop("max_retries", 3)
    retry_delay_initial_ms = params.pop("retry_delay_initial_ms", 1_000)
    retry_delay_max_ms = params.pop("retry_delay_max_ms", 10_000)
    use_fills_channel = params.pop("use_fills_channel", False)
    use_mm_mass_cancel = params.pop("use_mm_mass_cancel", False)
    use_spot_cash_position_reports = params.pop("use_spot_cash_position_reports", False)
    http_timeout_secs = params.pop("http_timeout_secs", None)

    data_config = None
    if client.use_data_client:
        data_kwargs = dict(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            api_passphrase=creds["api_passphrase"],
            is_demo=is_demo,
            instrument_provider=provider,
            update_instruments_interval_mins=client.update_instruments_interval_mins,
            max_retries=max_retries,
            retry_delay_initial_ms=retry_delay_initial_ms,
            retry_delay_max_ms=retry_delay_max_ms,
        )
        if instrument_types:
            data_kwargs["instrument_types"] = instrument_types
        if contract_types:
            data_kwargs["contract_types"] = contract_types
        if instrument_families:
            data_kwargs["instrument_families"] = tuple(instrument_families)
        if vip_level:
            data_kwargs["vip_level"] = vip_level
        if base_url_http:
            data_kwargs["base_url_http"] = base_url_http
        if base_url_ws:
            data_kwargs["base_url_ws"] = base_url_ws
        if http_timeout_secs is not None:
            data_kwargs["http_timeout_secs"] = http_timeout_secs
        data_config = OKXDataClientConfig(**data_kwargs)

    exec_config = None
    if client.use_exec_client:
        exec_kwargs = dict(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            api_passphrase=creds["api_passphrase"],
            is_demo=is_demo,
            instrument_provider=provider,
            max_retries=max_retries,
            retry_delay_initial_ms=retry_delay_initial_ms,
            retry_delay_max_ms=retry_delay_max_ms,
            use_spot_margin=use_spot_margin,
            use_fills_channel=use_fills_channel,
            use_mm_mass_cancel=use_mm_mass_cancel,
            use_spot_cash_position_reports=use_spot_cash_position_reports,
        )
        if instrument_types:
            exec_kwargs["instrument_types"] = instrument_types
        if contract_types:
            exec_kwargs["contract_types"] = contract_types
        if instrument_families:
            exec_kwargs["instrument_families"] = tuple(instrument_families)
        if margin_mode:
            exec_kwargs["margin_mode"] = margin_mode
        if base_url_http:
            exec_kwargs["base_url_http"] = base_url_http
        if base_url_ws:
            exec_kwargs["base_url_ws"] = base_url_ws
        if http_timeout_secs is not None:
            exec_kwargs["http_timeout_secs"] = http_timeout_secs
        exec_config = OKXExecClientConfig(**exec_kwargs)

    return data_config, exec_config


VENUE_BUILDERS = {
    "BINANCE": _build_binance_client_configs,
    "OKX": _build_okx_client_configs,
}


def build_trading_node_config(
    profile: AuroraRuntimeProfile,
) -> TradingNodeConfig:
    """
    Build a fully wired TradingNodeConfig for live Aurora trading.

    Credentials are resolved per client when this function executes.
    """

    profile.ensure_directories()
    data_clients: dict[str, object] = {}
    exec_clients: dict[str, object] = {}

    for client in profile.clients:
        builder = VENUE_BUILDERS[client.venue]
        provider_config = InstrumentProviderConfig(
            load_all=False,
            load_ids=client.instrument_ids,
        )
        data_config, exec_config = builder(client, provider_config)

        if data_config:
            data_clients[client.key] = data_config
        if exec_config:
            exec_clients[client.key] = exec_config

    return TradingNodeConfig(
        trader_id=TraderId(profile.trader_id),
        logging=LoggingConfig(
            log_level=profile.log_level,
            log_directory=str(profile.log_directory),
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
                path=str(profile.catalog_path),
                name="aurora_catalog",
            ),
        ],
        streaming=StreamingConfig(
            catalog_path=str(profile.catalog_path),
            flush_interval_ms=30_000,
            replace_existing=True,
        ),
        data_clients=data_clients,
        exec_clients=exec_clients,
        timeout_connection=30.0,
        timeout_reconciliation=15.0,
        timeout_portfolio=15.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )


def load_run_bundle(path: str | Path) -> tuple[AuroraHDGConfig, AuroraRuntimeProfile]:
    p = Path(path)
    data = read_config_data(p)
    strategy_cfg = build_strategy_config(data.get("strategy", data))
    runtime_raw = data.get("runtime")
    if runtime_raw is None:
        raise ValueError("Configuration file missing required `runtime` section.")
    runtime_profile = build_runtime_profile(
        runtime_raw,
        config_dir=p.parent,
        default_instrument=strategy_cfg.instrument_id,
    )
    return strategy_cfg, runtime_profile
