"""
Trading node configuration for FactorExp live trading.
Configures Nautilus Trader with Binance integration and portfolio monitoring.
"""

import os
from pathlib import Path

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


class TradingConfig:
    """Trading configuration container with dynamic account size support."""

    def __init__(self):
        self.trading_mode = os.getenv("TRADING_MODE", "testnet")
        self.is_testnet = self.trading_mode == "testnet"

        # Account size detection for dynamic configuration
        self.account_size_usd = self._detect_account_size()
        self.is_small_account = self.account_size_usd <= 500 if self.account_size_usd else False

        # Portfolio monitoring settings
        self.portfolio_update_interval = int(os.getenv("PORTFOLIO_UPDATE_INTERVAL_SEC", 5))
        self.enable_portfolio_alerts = os.getenv("ENABLE_PORTFOLIO_ALERTS", "true").lower() == "true"
        self.alert_threshold_pnl_pct = float(os.getenv("ALERT_THRESHOLD_PNL_PCT", 0.02))

        # Logging settings
        self.log_level = os.getenv("LOG_LEVEL", "DEBUG")  # Reduced from DEBUG to avoid excessive logging
        self.log_level_file = os.getenv("LOG_LEVEL_FILE", "DEBUG")
        self.enable_structured_logging = os.getenv("ENABLE_STRUCTURED_LOGGING", "true").lower() == "true"

        # Catalog persistence controls
        default_catalog_root = Path(__file__).resolve().parent.parent / "data" / "catalog"
        env_catalog = os.getenv("FACTOREXP_CATALOG_PATH")
        self.catalog_path = Path(env_catalog).expanduser() if env_catalog else default_catalog_root
        self.catalog_path.mkdir(parents=True, exist_ok=True)
        self.update_warmup_catalog = os.getenv("WARMUP_UPDATE_CATALOG", "true").lower() in {"1", "true", "yes", "on"}

        # Futures leverage controls
        self._futures_leverage_default = self._parse_leverage_default()
        self._futures_leverage_overrides = self._parse_leverage_overrides()

    def _detect_account_size(self) -> float | None:
        """Detect account size from environment variable."""
        account_size_env = os.getenv("ACCOUNT_SIZE_USD", "")
        try:
            if account_size_env and account_size_env.lower() not in ["", "standard"]:
                return float(account_size_env)
        except ValueError:
            pass
        return None

    def get_dynamic_notional_limits(self) -> dict[str, float]:
        """Calculate dynamic notional limits based on account size."""
        if self.account_size_usd and self.account_size_usd <= 500:
            # Small account limits - much more conservative
            base_limit = min(self.account_size_usd * 0.6, 300)  # 60% of account or $300 max
            return {
                "BTCUSDT-PERP.BINANCE": base_limit,
                "ETHUSDT-PERP.BINANCE": base_limit * 0.8,  # Slightly lower for ETH
            }
        elif self.account_size_usd and self.account_size_usd <= 2000:
            # Medium account limits
            base_limit = self.account_size_usd * 0.4  # 40% of account
            return {
                "BTCUSDT-PERP.BINANCE": base_limit,
                "ETHUSDT-PERP.BINANCE": base_limit * 0.8,
            }
        else:
            # Large account limits (original values)
            return {
                "BTCUSDT-PERP.BINANCE": 3000,
                "ETHUSDT-PERP.BINANCE": 2000,
            }

    def _parse_leverage_default(self) -> int | None:
        """Read FUTURES_LEVERAGE_DEFAULT from environment."""
        raw_default = os.getenv("FUTURES_LEVERAGE_DEFAULT")
        if raw_default in (None, "", "None"):
            return None

        try:
            # Allow floats like "2.0" but cast to int for Binance leverage API
            leverage = int(float(raw_default))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid FUTURES_LEVERAGE_DEFAULT value '{raw_default}'. Expected numeric leverage."
            ) from exc

        if leverage <= 0:
            raise ValueError("FUTURES_LEVERAGE_DEFAULT must be a positive integer.")

        return leverage

    def _parse_leverage_overrides(self) -> dict[str, int]:
        """
        Parse per-instrument leverage overrides from FUTURES_LEVERAGE_MAP.

        Expected format (case-insensitive instrument IDs):
            FUTURES_LEVERAGE_MAP=BTCUSDT-PERP.BINANCE=3,ETHUSDT-PERP.BINANCE=2
        Separators ',', ';', or whitespace are accepted between entries.
        """
        raw_map = os.getenv("FUTURES_LEVERAGE_MAP", "")
        overrides: dict[str, int] = {}
        if not raw_map:
            return overrides

        entries = [entry.strip() for entry in raw_map.replace(";", ",").split(",") if entry.strip()]
        for entry in entries:
            if "=" not in entry:
                raise ValueError(
                    f"Invalid FUTURES_LEVERAGE_MAP entry '{entry}'. Expected 'INSTRUMENT=LEVERAGE'."
                )
            instrument_str, leverage_str = (part.strip() for part in entry.split("=", 1))
            if not instrument_str:
                raise ValueError("FUTURES_LEVERAGE_MAP contains an empty instrument identifier.")
            try:
                leverage = int(float(leverage_str))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid leverage '{leverage_str}' for instrument '{instrument_str}'."
                ) from exc
            if leverage <= 0:
                raise ValueError(
                    f"Leverage override for '{instrument_str}' must be a positive integer."
                )
            overrides[instrument_str.upper()] = leverage

        return overrides

    def get_futures_leverages(
        self,
        instrument_ids: frozenset[InstrumentId],
    ) -> dict[BinanceSymbol, int] | None:
        """
        Build Binance leverage map for the configured instruments.

        Combines FUTURES_LEVERAGE_MAP overrides with FUTURES_LEVERAGE_DEFAULT fallback.
        Returns None when no leverage configuration is supplied.
        """
        if not instrument_ids:
            return None

        if not self._futures_leverage_overrides and self._futures_leverage_default is None:
            return None

        leverages: dict[BinanceSymbol, int] = {}
        for instrument_id in instrument_ids:
            # Accept overrides by full InstrumentId (includes venue) or by symbol without venue.
            override_key_full = str(instrument_id).upper()
            override_key_symbol = instrument_id.symbol.upper()

            leverage = self._futures_leverage_overrides.get(override_key_full)
            if leverage is None:
                leverage = self._futures_leverage_overrides.get(override_key_symbol)
            if leverage is None:
                leverage = self._futures_leverage_default

            if leverage is None:
                continue

            leverages[BinanceSymbol(instrument_id.symbol)] = leverage

        return leverages or None


def create_trading_node_config(api_credentials: dict[str, str | None], instruments: list[str] = None) -> TradingNodeConfig:
    """
    Create trading node configuration with dynamic risk management and precision instrument loading.
    
    Automatically adjusts risk limits based on account size:
    - Small accounts (≤$500): Conservative limits (60% of account)
    - Medium accounts (≤$2000): Moderate limits (40% of account)  
    - Large accounts (>$2000): Standard limits ($3000/$2000)
    
    Only loads data for instruments that will actually be traded, improving performance.
    
    Parameters
    ----------
    api_credentials : Dict[str, Optional[str]]
        API credentials dictionary containing api_key, api_secret, and testnet flag
    instruments : List[str], optional
        List of instrument strings to load data for (e.g. ['BTCUSDT-PERP.BINANCE'])
        If None, loads default instruments
        
    Returns
    -------
    TradingNodeConfig
        Configured trading node with precision instrument loading
    """
    config = TradingConfig()

    # Extract InstrumentIds from the instruments list for precision loading
    if instruments:
        instrument_ids = frozenset(InstrumentId.from_str(inst) for inst in instruments)
        print(f"📊 Configuring precise data subscription for: {instruments}")
    else:
        # Default instruments if none provided
        default_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
        instrument_ids = frozenset(InstrumentId.from_str(inst) for inst in default_instruments)
        print(f"📊 Using default instruments for data subscription: {default_instruments}")

    futures_leverages = config.get_futures_leverages(instrument_ids)

    if futures_leverages:
        symbols_preview = ", ".join(f"{symbol}={lv}x" for symbol, lv in futures_leverages.items())
        print(f"⚙️ Futures leverage overrides: {symbols_preview}")

    return TradingNodeConfig(
        trader_id=TraderId("FACTOREXP-LIVE-001"),

        data_engine=LiveDataEngineConfig(
            graceful_shutdown_on_exception=True,
        ),

        # Logging configuration with portfolio monitoring
        logging=LoggingConfig(
            log_level=config.log_level,
            log_level_file=config.log_level_file,
            log_directory="./data/logs",  # Organize application logs in data/logs directory
            log_file_format="json" if config.enable_structured_logging else None,
            log_colors=True,
            log_component_levels={
                "Strategy": "DEBUG",           # Strategy-level logging
                "FactorExp": "DEBUG",         # FactorExp indicator logging
                "Portfolio": "INFO",          # Native portfolio logging
                "RiskEngine": "INFO",         # Native risk engine logging
                "DataEngine": "INFO",         # Data engine logging
                "ExecEngine": "DEBUG",         # Execution engine logging
            }
        ),

        # Execution engine with enhanced reconciliation
        exec_engine=LiveExecEngineConfig(
            graceful_shutdown_on_exception=True,
            reconciliation=True,
            reconciliation_lookback_mins=1440,  # 24 hours
            inflight_check_interval_ms=5000,    # 5 seconds
            snapshot_orders=True,
            snapshot_positions=True,
            snapshot_positions_interval_secs=float(config.portfolio_update_interval),
            debug=True,
        ),

        # Dynamic Risk Engine with account-size-appropriate limits
        risk_engine=LiveRiskEngineConfig(
            graceful_shutdown_on_exception=True,
            bypass=False,  # Enable all risk checks for live trading
            max_order_submit_rate="20/00:00:01",      # Max 20 orders per second
            max_order_modify_rate="10/00:00:01",      # Max 10 modifications per second
            max_notional_per_order=config.get_dynamic_notional_limits(),  # Dynamic limits based on account size
            debug=True,  # Enable detailed risk logging
        ),

        # Cache configuration for portfolio tracking
        cache=CacheConfig(
            timestamps_as_iso8601=True,
            flush_on_start=False,
        ),

        catalogs=[
            DataCatalogConfig(
                path=str(config.catalog_path),
                name="warmup_catalog",
            ),
        ],

        # Streaming configuration - lightweight to avoid API rate limits
        streaming=StreamingConfig(
            catalog_path=str(config.catalog_path),  # Persist warmup/catalog data under ./data/catalog
            flush_interval_ms=30000,                # Write data every 30 seconds (less frequent)
            replace_existing=True,                  # Overwrite to avoid accumulation
        ),

        # Binance data client configuration
        data_clients={
            BINANCE: BinanceDataClientConfig(
                api_key=api_credentials["api_key"],
                api_secret=api_credentials["api_secret"],
                account_type=BinanceAccountType.USDT_FUTURE,
                testnet=api_credentials.get("testnet", True),
                update_instruments_interval_mins=60,
                use_agg_trade_ticks=False,  # Use raw trade data for accuracy
                use_vision_bars=True,
                use_vision_trades=True,
                http_max_retries=6,
                http_retry_initial_delay_ms=1_000,
                http_retry_max_delay_ms=30_000,
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,  # Only load specific instruments
                    load_ids=instrument_ids,  # Load only trading instruments
                ),
            ),
        },

        # Binance execution client configuration
        exec_clients={
            BINANCE: BinanceExecClientConfig(
                api_key=api_credentials["api_key"],
                api_secret=api_credentials["api_secret"],
                account_type=BinanceAccountType.USDT_FUTURE,
                testnet=api_credentials.get("testnet", True),
                max_retries=3,
                retry_delay_initial_ms=1_000,
                retry_delay_max_ms=10_000,
                use_position_ids=True,   # Use hedge mode (dual-side positioning)
                use_reduce_only=False,   # Disable reduce_only (incompatible with hedge mode)
                futures_leverages=futures_leverages,
                instrument_provider=InstrumentProviderConfig(
                    load_all=False,  # Only load specific instruments
                    load_ids=instrument_ids,  # Load only trading instruments
                ),
            ),
        },

        # Connection timeouts
        timeout_connection=30.0,
        timeout_reconciliation=15.0,
        timeout_portfolio=15.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )
