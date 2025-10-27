"""
FactorExp Live Trading Strategy

Pure FactorExp quantitative strategy for live trading with comprehensive risk management.

This strategy uses ONLY FactorExp expressions - no native Nautilus indicators.
All FactorExp operators have been verified against the actual implementation.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict
from typing import Optional

from factorexp_backtest.configs.config_loader import FactorConfigLoader
from factorexp_live_trading.components.warmup_catalog import WarmupCatalog
from factorexp_live_trading.components.warmup_catalog import WarmupCoverage

# Official strategy configuration
from factorexp_live_trading.config.strategy_config import FactorExpLiveStrategyConfig

from nautilus_trader.common.enums import LogColor
from nautilus_trader.common.component import TimeEvent

# FactorExp imports - VERIFIED to exist
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.events import PositionChanged
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.events import PositionOpened
from nautilus_trader.model.identifiers import PositionId

# Native risk management components
from nautilus_trader.trading.strategy import Strategy


@dataclass
class SegmentState:
    """State tracking for a single segment during live trading."""

    idx: int
    current_qty: float
    avg_entry_price: float
    current_equity: float
    initial_equity: float
    peak_equity: float
    cumulative_realized_pnl: float = 0.0
    frozen_until_ns: int = 0
    is_depleted: bool = False
    pending_target_qty: float = 0.0
    pending_timestamp_ns: int = 0

    def has_inventory(self) -> bool:
        """Return True if the segment currently holds exposure."""
        return abs(self.current_qty) > 0


class FactorExpLiveStrategy(Strategy):
    """
    Live trading strategy using verified FactorExp expressions with risk management.
    
    Uses only operators that have been verified to exist in the actual FactorExp implementation:
    - TS_Mean, TS_Std: Rolling mean and standard deviation
    - TS_Ref: Reference to previous values (lag functionality)
    - Mathematical operations: +, -, *, /, parentheses
    - Math functions: Max, Min, Abs (verified to exist)
    
    Includes comprehensive risk management and portfolio monitoring.
    """

    def __init__(self, config: FactorExpLiveStrategyConfig) -> None:
        """
        Initialize the FactorExp live trading strategy.
        
        Parameters
        ----------
        config : FactorExpLiveStrategyConfig
            Official Nautilus Trader strategy configuration
        """
        super().__init__(config)

        # Configuration is now available as self.config from parent Strategy class

        # Shared factor configuration (loaded from research YAML)
        self._factor_config_path = self._resolve_config_path(config.factor_config_path)
        self._factor_id = config.factor_id
        self._factor_loader: FactorConfigLoader | None = None
        self._factor_config = None
        self._factor_defaults: dict | None = None
        self._risk_config = None
        self._execution_config = None
        self._position_scale = Decimal("1.0")
        self._factor_indicator: FactorExpIndicator | None = None
        self._factor_expression: str | None = None
        self._factor_requires_extended = False
        self._warmup_bars = 0  # Will be set after indicator creation based on required_history
        self._latest_factor_value: float | None = None

        # Copy factor overrides from config (will be validated against defaults)
        self._zscore_period = int(config.zscore_period)
        self._min_signal_magnitude = float(config.min_signal_magnitude)

        # Segment ledger (Phase 3 parity)
        self._segment_count = 96
        self._segment_states: list[SegmentState] = []
        self._segment_index = 0
        self._bar_duration_ns = 0
        self._freeze_duration_bars = 96
        self._long_position_id: Optional[PositionId] = None
        self._short_position_id: Optional[PositionId] = None
        self._order_to_segment: Dict[str, SegmentState] = {}
        self._order_pending_delta: Dict[str, float] = {}
        self._segment_rotation_counter = 0
        self._last_bar_close: float | None = None
        self._instrument = None
        self._max_leverage = 2.0
        self._segment_stop_loss_pct = 0.05
        self._min_order_size = 0.001

        # Strategy monitoring counters
        self._bar_count = 0
        self._trade_count_timer_name: str | None = None
        self._trade_count_interval_ns = 30 * 1_000_000_000  # 30 seconds in nanoseconds
        self._trade_count_in_window = 0
        self._trade_count_window_start_ns: int | None = None
        self._trade_count_last_flush_ns: int | None = None

        # Data request coordination flag (set by trading system)
        self._should_request_historical_data = True
        self._warmup_catalog: WarmupCatalog | None = None
        self._warmup_catalog_coverage: WarmupCoverage | None = None

        # IMMEDIATE TEST: Verify logger works during strategy instantiation
        print(f"🔍 [TEST] FactorExpLiveStrategy.__init__() called for {config.instrument_id}")
        if hasattr(self, "log") and self.log:
            self.log.info(f"🔍 [TEST] FactorExpLiveStrategy logger initialized for {config.instrument_id}")
        else:
            print("❌ [TEST] FactorExpLiveStrategy logger NOT available during __init__")

    def on_start(self):
        """Actions to be performed when the strategy is started."""
        # IMMEDIATE TEST: Verify on_start is called
        print(f"🔍 [TEST] FactorExpLiveStrategy.on_start() called for {self.config.instrument_id}")
        self.log.info("🔍 [TEST] on_start() method called")
        self.log.info(f"FactorExpLiveStrategy starting for {self.config.instrument_id}")

        instrument = self.cache.instrument(self.config.instrument_id)
        if instrument is None:
            self.log.error(f"Could not find instrument {self.config.instrument_id}")
            self.stop()
            return
        self._instrument = instrument
        self._long_position_id = PositionId(f"{self.config.instrument_id}-FACTOREXP-LONG")
        self._short_position_id = PositionId(f"{self.config.instrument_id}-FACTOREXP-SHORT")

        # Log capital management configuration
        self.log.info(
            f"Capital Management: max_account_usage={self.config.max_account_usage_pct:.1%}, "
            f"max_absolute_exposure=${self.config.max_absolute_exposure:,.0f}, "
            f"position_risk={self.config.position_risk_pct:.1%}"
        )

        # Load shared factor definition
        if not self._load_factor_definition():
            self.stop()
            return

        # Verify extended bar support if required by the factor
        if self._factor_requires_extended and not self._supports_extended_bars():
            self.log.error(
                f"Factor '{self._factor_config.name}' requires extended bar fields "
                "but the current build does not expose them."
            )
            self.stop()
            return

        # Build and register the FactorExp indicator graph
        try:
            self._setup_factor_graph()
        except Exception:
            self.stop()
            return

        self.log.info(
            f"Factor graph ready | factor_id={self._factor_id}, "
            f"warmup={self._warmup_bars} bars"
        )

        if not self._initialize_segments():
            self.stop()
            return

        # Show initial portfolio state (following official patterns)
        self.show_portfolio_info("Portfolio state (Strategy started):")

        # Initialize trade tick counting timer (30-second cadence)
        self._trade_count_in_window = 0
        self._trade_count_window_start_ns = None
        self._trade_count_last_flush_ns = self._clock.timestamp_ns()
        timer_name = f"{self.id.value}-trade-count"
        try:
            self.clock.set_timer(
                name=timer_name,
                interval=timedelta(seconds=30),
                callback=self._on_trade_count_timer,
                fire_immediately=False,
            )
            self._trade_count_timer_name = timer_name
            self.log.info("Trade tick monitor started (30s interval).")
        except Exception as exc:
            self._trade_count_timer_name = None
            self.log.warning(f"Unable to start trade tick monitor: {exc}")

    def _resolve_config_path(self, config_path: str) -> Path:
        """
        Resolve factor config path relative to repository root.

        Parameters
        ----------
        config_path : str
            Path provided in the strategy configuration.

        Returns
        -------
        Path
            Absolute path to the factor YAML file.
        """
        path = Path(config_path)
        if path.is_absolute():
            return path
        repo_root = Path(__file__).resolve().parents[2]
        return (repo_root / path).resolve()

    def _load_factor_definition(self) -> bool:
        """Load FactorExp definition shared with the backtest."""
        try:
            self._factor_loader = FactorConfigLoader(self._factor_config_path)
        except Exception as exc:
            self.log.error(
                f"Failed to load factor catalog '{self._factor_config_path}': {exc}"
            )
            return False

        try:
            self._factor_config = self._factor_loader.get_factor(self._factor_id)
        except KeyError:
            available = ", ".join(self._factor_loader.list_factors())
            self.log.error(
                f"Factor '{self._factor_id}' not found in "
                f"{self._factor_config_path}. Available factors: {available}"
            )
            return False

        self._factor_defaults = self._factor_loader.get_defaults() or {}
        defaults = self._factor_defaults

        # Shared risk/execution characteristics from backtest catalog
        self._risk_config = getattr(self._factor_loader, "risk_config", None)
        self._execution_config = getattr(self._factor_loader, "execution_config", None)
        if self._execution_config:
            self._min_order_size = float(self._execution_config.min_order_size)

        # Synchronise shared parameters with backtest defaults (allow overrides)
        default_zscore = int(defaults.get("zscore_period", self._zscore_period))
        if self._zscore_period != default_zscore:
            self.log.warning(
                f"Using live z-score period override ({self._zscore_period}) "
                f"instead of catalog default ({default_zscore})."
            )
        else:
            self._zscore_period = default_zscore

        # Note: _warmup_bars will be set after indicator creation based on required_history
        # This ensures we get the true warmup requirement accounting for nested windows
        self._factor_expression = self._factor_config.expression
        self._factor_requires_extended = bool(self._factor_config.requires_extended)

        expression_preview = (
            self._factor_expression.replace(" ", "")[:120] + "..."
            if self._factor_expression and len(self._factor_expression) > 120
            else self._factor_expression
        )
        self.log.info(
            f"Loaded factor '{self._factor_config.name}' "
            f"(requires_extended={self._factor_requires_extended}) | "
            f"expression={expression_preview}"
        )

        return True

    def _supports_extended_bars(self) -> bool:
        """Check whether the runtime exposes FactorExp extended bar fields."""
        try:
            from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS

            if EXTENDED_BAR_FIELD_SPECS:
                return True
        except Exception:
            pass

        # Fallback check for amt field presence (most common extended requirement)
        return hasattr(Bar, "amt")

    def _setup_factor_graph(self):
        """Instantiate and register the FactorExp indicator based on YAML config."""
        try:
            # Create indicator without period parameter - it will be auto-detected
            # from the expression tree accounting for nested windows
            self._factor_indicator = FactorExpIndicator(
                expression=self._factor_expression,
                name=f"{self._factor_config.factor_id.upper()}",
            )

            # Get the true warmup requirement from the indicator
            # This accounts for nested window operators correctly
            self._warmup_bars = self._factor_indicator.required_history

            self.log.info(
                f"Indicator created | required_history={self._warmup_bars} bars "
                f"(auto-detected from expression tree)"
            )
        except Exception as exc:
            self.log.error(
                f"Failed to instantiate FactorExp indicator for factor "
                f"'{self._factor_id}': {exc}"
            )
            raise

        try:
            self.register_indicator_for_bars(self.config.bar_type, self._factor_indicator)
        except Exception as exc:
            self.log.error(
                f"Failed to register FactorExp indicator for {self.config.bar_type}: {exc}"
            )
            raise

        if self._should_request_historical_data:
            try:
                self._request_factor_warmup()
            except Exception:
                # Error already logged in _request_factor_warmup
                raise
        else:
            self.log.info(
                f"Skipping historical warmup for {self.config.bar_type} "
                "(already requested by another strategy)."
            )

        self.subscribe_bars(self.config.bar_type)

    def _request_factor_warmup(self):
        """Request historical bars to warm up the factor indicator."""
        if self._warmup_bars <= 0:
            return

        # TODO: Binance adapter 应补充批量/回退机制以保障大窗口 warmup，此处暂依赖上游改进
        bar_type = self.config.bar_type
        bar_type_str = str(bar_type)
        is_internal = bar_type.is_internally_aggregated()

        if "15-MINUTE" in bar_type_str:
            delta = timedelta(minutes=self._warmup_bars * 15)
        elif "5-MINUTE" in bar_type_str:
            delta = timedelta(minutes=self._warmup_bars * 5)
        elif "1-HOUR" in bar_type_str:
            delta = timedelta(hours=self._warmup_bars)
        elif "1-DAY" in bar_type_str or "DAILY" in bar_type_str:
            delta = timedelta(days=self._warmup_bars)
        else:
            delta = timedelta(minutes=self._warmup_bars)

        now = self._clock.utc_now()
        start_time = now - delta

        request_msg = (
            f"Requesting {self._warmup_bars} historical bars for "
            f"{bar_type} warmup (start={start_time.isoformat()} UTC)."
        )
        if is_internal:
            request_msg += " (aggregated)"
        self.log.info(request_msg)

        catalog_update = os.getenv("WARMUP_UPDATE_CATALOG", "true").lower() in {"1", "true", "yes", "on"}
        warmup_params: dict[str, object] | None = None
        coverage = None
        request_bar_types: list[BarType] = [bar_type]

        catalog = self._get_warmup_catalog()
        if catalog is not None:
            try:
                coverage = catalog.summarize_bar_coverage(
                    bar_type=bar_type,
                    start=start_time,
                    end=now,
                )
                self._warmup_catalog_coverage = coverage

                if coverage.covered:
                    self.log.info(
                        f"Warmup catalog already covers requested range "
                        f"({start_time.isoformat()} → {now.isoformat()} UTC).",
                    )
                else:
                    self.log.info(
                        f"Warmup catalog missing {len(coverage.missing)} interval(s) "
                        f"for {bar_type}; requesting gap fill.",
                    )

                warmup_params = {
                    "warmup_catalog_start_ns": coverage.start_ns,
                    "warmup_catalog_end_ns": coverage.end_ns,
                    "warmup_catalog_missing_ns": coverage.missing,
                }
            except Exception as exc:
                self.log.warning(f"Unable to inspect warmup catalog coverage: {exc}")
                self._warmup_catalog_coverage = None

            catalog_update = catalog.update_enabled

        if is_internal:
            composite_base = self._build_time_composite_bar_type(bar_type)
            if composite_base is not None and composite_base != bar_type:
                request_bar_types = [composite_base, bar_type]
                self.log.info(
                    f"Warmup 将优先使用 {composite_base} 作为 EXTERNAL 基础条目，再聚合成 {bar_type}。"
                )

        try:
            if is_internal:
                self.request_aggregated_bars(
                    request_bar_types,
                    start=start_time,
                    end=now,
                    update_subscriptions=True,
                    update_catalog=catalog_update,
                    params=warmup_params,
                )
            else:
                self.request_bars(
                    bar_type=bar_type,
                    start=start_time,
                    end=now,
                    update_catalog=catalog_update,
                    params=warmup_params,
                )
        except Exception as exc:
            self.log.error(
                f"Historical warmup request failed for {bar_type}: {exc}"
            )
            raise

    def _get_warmup_catalog(self) -> WarmupCatalog | None:
        if self._warmup_catalog is not None:
            return self._warmup_catalog

        try:
            self._warmup_catalog = WarmupCatalog()
        except Exception as exc:
            self.log.warning(f"Warmup catalog unavailable ({exc}).")
            self._warmup_catalog = None

        return self._warmup_catalog

    def _build_time_composite_bar_type(self, bar_type: BarType) -> BarType | None:
        """
        为时间聚合的 INTERNAL BarType 构造一个带 EXTERNAL 基线的复合类型，
        以便 `request_aggregated_bars` 触发 REST/Vision K线下载。
        """
        if not bar_type.is_internally_aggregated():
            return None

        if bar_type.is_composite():
            return bar_type

        spec = bar_type.spec
        if spec.aggregation != BarAggregation.MINUTE:
            # 目前仅对 MINUTE 系列做 Vision 复用，其它聚合（Tick/Volume 等）仍回落到成交路径
            return None

        base_spec = BarSpecification(
            step=1,
            aggregation=BarAggregation.MINUTE,
            price_type=spec.price_type,
        )

        try:
            composite = BarType.new_composite(
                bar_type.instrument_id,
                spec,
                AggregationSource.INTERNAL,
                base_spec.step,
                base_spec.aggregation,
                AggregationSource.EXTERNAL,
            )
        except Exception as exc:
            self.log.warning(
                "无法构造复合 BarType 以启用 Vision warmup，继续使用成交聚合。原因: %s",
                exc,
            )
            return None

        return composite


    def _initialize_segments(self) -> bool:
        """Create 96 SegmentState entries mirroring the backtest ledger."""
        account = self.cache.account_for_venue(self.config.instrument_id.venue)
        if account is None:
            self.log.error(
                f"Cannot create segment ledger without account on venue {self.config.instrument_id.venue}"
            )
            return False

        instrument = self._instrument
        if instrument is None:
            self.log.error("Instrument not cached during segment initialization")
            return False

        quote_currency = instrument.quote_currency
        balance_total = account.balance_total(quote_currency)
        if not balance_total:
            self.log.error(f"Unable to determine total balance for {quote_currency}")
            return False

        total_equity = float(balance_total)
        if total_equity <= 0:
            self.log.error(f"Account equity for {quote_currency} is non-positive: {total_equity}")
            return False

        equity_per_segment = total_equity / self._segment_count
        self._segment_states = [
            SegmentState(
                idx=idx,
                current_qty=0.0,
                avg_entry_price=0.0,
                current_equity=equity_per_segment,
                initial_equity=equity_per_segment,
                peak_equity=equity_per_segment,
            )
            for idx in range(self._segment_count)
        ]
        self._segment_index = 0
        self._segment_rotation_counter = 0

        if self._risk_config:
            self._max_leverage = float(self._risk_config.max_position_size)
            self._segment_stop_loss_pct = float(self._risk_config.stop_loss)
            self._freeze_duration_bars = int(
                self._risk_config.max_rebalance_interval or self._freeze_duration_bars
            )
        else:
            self._max_leverage = 2.0
            self._segment_stop_loss_pct = 0.05

        if self._execution_config:
            self._min_order_size = float(self._execution_config.min_order_size)

        self._bar_duration_ns = self._calculate_bar_duration_ns()
        self.log.info(
            f"Initialized {self._segment_count} segments | equity per segment={equity_per_segment:.2f}, "
            f"max_leverage={self._max_leverage:.2f}, stop_loss={self._segment_stop_loss_pct:.2%}, "
            f"freeze={self._freeze_duration_bars} bars"
        )
        return True

    def _calculate_bar_duration_ns(self) -> int:
        """Derive bar duration in nanoseconds to align freeze timers."""
        from nautilus_trader.model.enums import BarAggregation

        try:
            bar_spec = self.config.bar_type.spec
        except AttributeError:
            # Fallback: assume 15-minute bars if spec unavailable
            fifteen_minutes_ns = 15 * 60 * 1_000_000_000
            return fifteen_minutes_ns

        if bar_spec.aggregation == BarAggregation.MINUTE:
            return bar_spec.step * 60 * 1_000_000_000
        if bar_spec.aggregation == BarAggregation.HOUR:
            return bar_spec.step * 60 * 60 * 1_000_000_000
        if bar_spec.aggregation == BarAggregation.SECOND:
            return bar_spec.step * 1_000_000_000

        # Default to 15-minute cadence when aggregation is unknown
        return 15 * 60 * 1_000_000_000

    def _get_segment_equity(self, state: SegmentState, price: float) -> float:
        """
        Compute TRUE equity = cash (realized) + unrealized PnL for a segment.

        Parameters
        ----------
        state : SegmentState
            Segment to evaluate.
        price : float
            Current market price.
        """
        if not state.has_inventory():
            return state.current_equity

        unrealized = (price - state.avg_entry_price) * state.current_qty
        return state.current_equity + unrealized

    def _submit_segment_target(self, state: SegmentState, target_qty: float) -> bool:
        """
        Route orders so the segment converges to target quantity.

        The Binance hedge-mode adapter only exposes two positions (LONG/SHORT).
        We therefore split adjustments into:
        - Reduce existing exposure on one side (reduce_only=True)
        - Open/extend exposure on the other side
        """
        if self._instrument is None:
            self.log.error("Cannot submit orders without cached instrument")
            return False

        current_qty = state.current_qty
        delta = target_qty - current_qty
        if abs(delta) < self._min_order_size:
            self.log.debug(
                f"Seg{state.idx}: delta {delta:.6f} below min order {self._min_order_size}, skipping"
            )
            return False

        operations: list[tuple[OrderSide, float, PositionId, bool]] = []

        if delta > 0:
            remaining = delta
            if current_qty < 0:
                cover_qty = min(abs(current_qty), remaining)
                if cover_qty >= self._min_order_size:
                    operations.append((OrderSide.BUY, cover_qty, self._short_position_id, True))
                remaining -= cover_qty
            if remaining >= self._min_order_size:
                operations.append((OrderSide.BUY, remaining, self._long_position_id, False))
        else:
            remaining = abs(delta)
            if current_qty > 0:
                reduce_qty = min(current_qty, remaining)
                if reduce_qty >= self._min_order_size:
                    operations.append((OrderSide.SELL, reduce_qty, self._long_position_id, True))
                remaining -= reduce_qty
            if remaining >= self._min_order_size:
                operations.append((OrderSide.SELL, remaining, self._short_position_id, False))

        if not operations:
            return False

        submitted = False
        timestamp_ns = self._clock.timestamp_ns()

        for side, qty, position_id, reduce_only in operations:
            if qty <= 0 or position_id is None:
                continue

            qty_obj = self._instrument.make_qty(Decimal(str(qty)))
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=side,
                quantity=qty_obj,
                reduce_only=reduce_only,
            )

            self.submit_order(order, position_id=position_id)

            client_id = str(order.client_order_id)
            self._order_to_segment[client_id] = state
            signed_delta = qty if side == OrderSide.BUY else -qty
            self._order_pending_delta[client_id] = signed_delta

            submitted = True

            self.log.info(
                f"Seg{state.idx}: submit {side.name} qty={qty:.6f} reduce_only={reduce_only} "
                f"target={target_qty:.6f} current={current_qty:.6f}"
            )

        if submitted:
            state.pending_target_qty = target_qty
            state.pending_timestamp_ns = timestamp_ns

        return submitted

    def _apply_fill_to_segment(self, state: SegmentState, event: OrderFilled) -> None:
        """Update segment ledger with fill information."""
        price = float(event.last_px.as_decimal())
        qty = float(event.last_qty.as_decimal())
        if qty <= 0:
            return

        if event.order_side == OrderSide.BUY:
            self._apply_buy_fill(state, qty, price)
        else:
            self._apply_sell_fill(state, qty, price)

        self._apply_commission_to_segment(state, event.commission)

    def _apply_buy_fill(self, state: SegmentState, qty: float, price: float) -> None:
        """Handle BUY fills for a segment."""
        remaining = qty

        if state.current_qty < 0:
            cover_qty = min(abs(state.current_qty), remaining)
            realized = (state.avg_entry_price - price) * cover_qty
            state.current_qty += cover_qty
            state.current_equity += realized
            state.cumulative_realized_pnl += realized
            remaining -= cover_qty

            if abs(state.current_qty) < 1e-9:
                state.current_qty = 0.0
                state.avg_entry_price = 0.0

        if remaining <= 0:
            return

        if state.current_qty <= 0:
            # Opening fresh long exposure
            state.current_qty = remaining
            state.avg_entry_price = price
        else:
            new_qty = state.current_qty + remaining
            state.avg_entry_price = (
                (state.current_qty * state.avg_entry_price) + (remaining * price)
            ) / new_qty
            state.current_qty = new_qty

    def _apply_sell_fill(self, state: SegmentState, qty: float, price: float) -> None:
        """Handle SELL fills for a segment."""
        remaining = qty

        if state.current_qty > 0:
            reduce_qty = min(state.current_qty, remaining)
            realized = (price - state.avg_entry_price) * reduce_qty
            state.current_qty -= reduce_qty
            state.current_equity += realized
            state.cumulative_realized_pnl += realized
            remaining -= reduce_qty

            if abs(state.current_qty) < 1e-9:
                state.current_qty = 0.0
                state.avg_entry_price = 0.0

        if remaining <= 0:
            return

        if state.current_qty >= 0:
            # Opening fresh short exposure
            state.current_qty = -remaining
            state.avg_entry_price = price
        else:
            total_short = abs(state.current_qty) + remaining
            state.avg_entry_price = (
                (abs(state.current_qty) * state.avg_entry_price) + (remaining * price)
            ) / total_short
            state.current_qty = -total_short

    def _apply_commission_to_segment(self, state: SegmentState, commission) -> None:
        """Adjust segment equity and PnL for fill commission."""
        if commission is None:
            return

        try:
            fee = float(commission.as_decimal())
        except Exception:
            self.log.warning("Unable to parse commission from fill event")
            return

        if fee == 0.0:
            return

        state.current_equity -= fee
        state.cumulative_realized_pnl -= fee

    def _check_segment_risk(self, state: SegmentState, price: float) -> bool:
        """
        Evaluate trailing drawdown risk on a segment.

        Returns True if action was taken (segment forced flat / frozen).
        """
        if state.is_depleted:
            return False

        total_equity = self._get_segment_equity(state, price)

        if total_equity > state.peak_equity:
            state.peak_equity = total_equity

        drawdown = state.peak_equity - total_equity
        threshold = state.peak_equity * self._segment_stop_loss_pct

        if drawdown > threshold:
            self.log.warning(
                f"Seg{state.idx}: stop-loss triggered | drawdown={drawdown:.2f} "
                f"threshold={threshold:.2f} peak={state.peak_equity:.2f} equity={total_equity:.2f}"
            )
            self._force_flat(state)
            state.frozen_until_ns = self._clock.timestamp_ns() + (
                self._freeze_duration_bars * self._bar_duration_ns
            )
            state.peak_equity = max(total_equity, state.current_equity)
            state.pending_target_qty = 0.0
            state.pending_timestamp_ns = 0
            return True

        if total_equity <= 0:
            self.log.error(
                f"Seg{state.idx}: equity depleted ({total_equity:.2f}), forcing flat and marking depleted"
            )
            self._force_flat(state)
            state.is_depleted = True
            state.frozen_until_ns = self._clock.timestamp_ns() + (
                self._freeze_duration_bars * self._bar_duration_ns
            )
            return True

        return False

    def _force_flat(self, state: SegmentState) -> None:
        """Issue orders to fully flatten a segment."""
        if not state.has_inventory():
            return

        self.log.warning(f"Seg{state.idx}: forcing flat | qty={state.current_qty:.6f}")
        self._submit_segment_target(state, 0.0)

    def _rebalance_segment(self, state: SegmentState, price: float, factor_value: float) -> None:
        """
        Rebalance a single segment based on FactorExp signal.

        Parameters
        ----------
        state : SegmentState
            Segment to rebalance.
        price : float
            Current market price.
        factor_value : float
            Clip(ZScore(...)) reading shared with backtest.
        """
        if state.is_depleted:
            return

        now_ns = self._clock.timestamp_ns()
        if state.frozen_until_ns and now_ns < state.frozen_until_ns:
            return
        if state.frozen_until_ns and now_ns >= state.frozen_until_ns:
            state.frozen_until_ns = 0
            self.log.info(f"Seg{state.idx}: unfreezed | equity={state.current_equity:.2f}")

        if price <= 0:
            self.log.error("Price is non-positive, skipping rebalance")
            return

        segment_equity = self._get_segment_equity(state, price)
        if segment_equity <= 0:
            self.log.error(
                f"Seg{state.idx}: non-positive equity ({segment_equity:.2f}), freezing segment"
            )
            state.is_depleted = True
            self._force_flat(state)
            return

        target_weight = factor_value * float(self._position_scale)
        target_notional = target_weight * segment_equity
        max_notional = abs(segment_equity) * self._max_leverage

        if target_notional > max_notional:
            target_notional = max_notional
        elif target_notional < -max_notional:
            target_notional = -max_notional

        target_qty = target_notional / price

        if segment_equity > state.peak_equity:
            state.peak_equity = segment_equity

        submitted = self._submit_segment_target(state, target_qty)
        if submitted:
            self.log.debug(
                f"Seg{state.idx}: factor={factor_value:.4f} equity={segment_equity:.2f} "
                f"current={state.current_qty:.6f} target={target_qty:.6f}"
            )

    def _log_segment_rotation(self, price: float) -> None:
        """Summarize ledger health at rotation boundaries."""
        active = sum(1 for s in self._segment_states if s.has_inventory())
        frozen = sum(
            1 for s in self._segment_states if s.frozen_until_ns > self._clock.timestamp_ns()
        )
        depleted = sum(1 for s in self._segment_states if s.is_depleted)

        total_equity = sum(self._get_segment_equity(s, price) for s in self._segment_states)

        self.log.info(
            f"Segment rotation #{self._segment_rotation_counter}: active={active}, "
            f"frozen={frozen}, depleted={depleted}, total_equity={total_equity:.2f}"
        )

    def _on_trade_count_timer(self, event: TimeEvent) -> None:
        self._flush_trade_count(event.ts_event, reason="timer")

    def _flush_trade_count(self, end_ns: int, reason: str) -> None:
        window_start_ns = self._trade_count_window_start_ns
        if window_start_ns is None:
            window_start_ns = self._trade_count_last_flush_ns
            if window_start_ns is None:
                window_start_ns = max(end_ns - self._trade_count_interval_ns, 0)

        start_iso = datetime.fromtimestamp(
            window_start_ns / 1_000_000_000, tz=timezone.utc
        ).isoformat()
        end_iso = datetime.fromtimestamp(end_ns / 1_000_000_000, tz=timezone.utc).isoformat()

        self.log.info(
            f"Trade ticks [{start_iso} → {end_iso}] count={self._trade_count_in_window} ({reason})"
        )

        self._trade_count_in_window = 0
        self._trade_count_window_start_ns = None
        self._trade_count_last_flush_ns = end_ns

    def on_quote_tick(self, tick: QuoteTick):
        """Handle quote tick data."""
        # TODO: 恢复 quote tick 订阅，并在此实现逐笔风控检查

    def on_trade_tick(self, tick: TradeTick):
        """Handle trade tick data."""
        if self._trade_count_window_start_ns is None:
            self._trade_count_window_start_ns = tick.ts_event
        self._trade_count_in_window += 1

    def on_bar(self, bar: Bar):
        """
        Handle bar data with 96-segment ledger logic.

        Parameters
        ----------
        bar : Bar
            The received bar data
        """
        if not self._segment_states:
            self.log.debug("Segments not initialized yet")
            return

        if not self._indicators_ready():
            self.log.debug("Indicators not ready yet")
            return

        self._bar_count += 1
        price = float(bar.close.as_decimal())
        self._last_bar_close = price

        raw_value = float(self._factor_indicator.value)
        factor_value = raw_value

        if abs(factor_value) < self._min_signal_magnitude:
            factor_value = 0.0

        self._latest_factor_value = factor_value

        bar_time = datetime.fromtimestamp(
            bar.ts_event / 1_000_000_000, tz=timezone.utc
        ).isoformat()
        self.log.info(
            f"Factor value @ {bar_time}: raw={raw_value:.6f}, effective={factor_value:.6f}, close={price:.4f}"
        )

        # Periodic portfolio monitoring (every 10 bars to avoid noise)
        if self._bar_count % 10 == 0:
            self.show_portfolio_info(f"Portfolio state (Bar {self._bar_count})")

        # Run risk checks on all segments with inventory
        risk_triggered = 0
        for state in self._segment_states:
            if state.has_inventory() and self._check_segment_risk(state, price):
                risk_triggered += 1

        if risk_triggered:
            self.log.warning(f"Risk engine flattened {risk_triggered} segment(s) this bar")

        # Rebalance current segment according to rotation
        segment = self._segment_states[self._segment_index]
        self._rebalance_segment(segment, price, factor_value)

        # Rotate to next segment (96 bar cadence)
        self._segment_index = (self._segment_index + 1) % self._segment_count
        if self._segment_index == 0:
            self._segment_rotation_counter += 1
            self._log_segment_rotation(price)

    def _indicators_ready(self) -> bool:
        """Check if the FactorExp indicator has sufficient data."""
        indicator = self._factor_indicator
        return bool(
            indicator
            and indicator.initialized
            and indicator.count >= indicator.required_history
        )

    def on_stop(self):
        """Stop hook ensuring segment ledger is flattened."""
        now_ns = self._clock.timestamp_ns()
        self._flush_trade_count(now_ns, reason="stop")
        if self._trade_count_timer_name:
            try:
                self.clock.cancel_timer(self._trade_count_timer_name)
            except Exception as exc:
                self.log.warning(f"Unable to cancel trade count timer: {exc}")
            self._trade_count_timer_name = None

        self.log.info("FactorExpLiveStrategy stopped")
        self.show_portfolio_info("Portfolio state (Strategy stopped)")

        for state in self._segment_states:
            if state.has_inventory():
                self._force_flat(state)

        self._order_to_segment.clear()
        self._order_pending_delta.clear()

        if not self.portfolio.is_completely_flat():
            self.log.info("Closing all positions on strategy stop")
            self.close_all_positions(self.config.instrument_id)

    def on_reset(self):
        """Reset strategy state and clear segment ledger caches."""
        self._order_to_segment.clear()
        self._order_pending_delta.clear()
        self._segment_index = 0
        self._segment_rotation_counter = 0
        self._latest_factor_value = None
        self._last_bar_close = None

        for state in self._segment_states:
            state.current_qty = 0.0
            state.avg_entry_price = 0.0
            state.current_equity = state.initial_equity
            state.peak_equity = state.initial_equity
            state.cumulative_realized_pnl = 0.0
            state.frozen_until_ns = 0
            state.is_depleted = False
            state.pending_target_qty = 0.0
            state.pending_timestamp_ns = 0

    def on_save(self) -> dict:
        """Persist ledger state for warm restarts."""
        return {
            "last_bar_close": self._last_bar_close,
            "latest_factor_value": self._latest_factor_value,
            "segments": [
                {
                    "idx": state.idx,
                    "current_qty": state.current_qty,
                    "avg_entry_price": state.avg_entry_price,
                    "current_equity": state.current_equity,
                    "peak_equity": state.peak_equity,
                    "cumulative_realized_pnl": state.cumulative_realized_pnl,
                    "frozen_until_ns": state.frozen_until_ns,
                    "is_depleted": state.is_depleted,
                }
                for state in self._segment_states
            ],
        }

    def on_load(self, state: dict):
        """Restore ledger state after serialization."""
        self._last_bar_close = state.get("last_bar_close")
        self._latest_factor_value = state.get("latest_factor_value")

        segments_data = state.get("segments", [])
        if segments_data and len(segments_data) == len(self._segment_states):
            for saved, current in zip(segments_data, self._segment_states):
                current.current_qty = saved.get("current_qty", 0.0)
                current.avg_entry_price = saved.get("avg_entry_price", 0.0)
                current.current_equity = saved.get("current_equity", current.initial_equity)
                current.peak_equity = saved.get("peak_equity", current.initial_equity)
                current.cumulative_realized_pnl = saved.get("cumulative_realized_pnl", 0.0)
                current.frozen_until_ns = saved.get("frozen_until_ns", 0)
                current.is_depleted = saved.get("is_depleted", False)
                current.pending_target_qty = current.current_qty
                current.pending_timestamp_ns = 0

    def _get_current_notional_exposure(self) -> float | None:
        """
        Get current notional exposure for risk management.
        
        Returns
        -------
        float or None
            Current notional exposure in quote currency
        """
        try:
            # Get current position
            if self.portfolio.is_flat(self.config.instrument_id):
                return 0.0

            position = self.portfolio.position(self.config.instrument_id)
            if not position:
                return 0.0

            # Get current market price
            quote_tick = self.cache.quote_tick(self.config.instrument_id)
            if quote_tick:
                current_price = float(quote_tick.bid_price + quote_tick.ask_price) / 2
            else:
                trade_tick = self.cache.trade_tick(self.config.instrument_id)
                if trade_tick:
                    current_price = float(trade_tick.price)
                else:
                    self.log.warning("Cannot determine current price for exposure calculation")
                    return None

            # Calculate notional exposure
            notional_exposure = abs(float(position.quantity)) * current_price
            return notional_exposure

        except Exception as e:
            self.log.error(f"Error calculating current exposure: {e}")
            return None

    def show_portfolio_info(self, intro_message: str = ""):
        """
        Display current portfolio information using native Nautilus Trader patterns.
        Based on official example: examples/backtest/example_05_using_portfolio/strategy.py
        """
        if intro_message:
            self.log.info(f"====== {intro_message} ======")

        # POSITION information
        self.log.info("Portfolio -> Position information:", color=LogColor.BLUE)
        is_flat = self.portfolio.is_flat(self.config.instrument_id)
        self.log.info(f"Is flat: {is_flat}", color=LogColor.BLUE)

        net_position = self.portfolio.net_position(self.config.instrument_id)
        self.log.info(f"Net position: {net_position} contract(s)", color=LogColor.BLUE)

        net_exposure = self.portfolio.net_exposure(self.config.instrument_id)
        self.log.info(f"Net exposure: {net_exposure}", color=LogColor.BLUE)

        active_segments = sum(1 for s in self._segment_states if s.has_inventory())
        frozen_segments = sum(
            1 for s in self._segment_states if s.frozen_until_ns > self._clock.timestamp_ns()
        )
        depleted_segments = sum(1 for s in self._segment_states if s.is_depleted)
        self.log.info(
            f"Segments -> active={active_segments}, frozen={frozen_segments}, depleted={depleted_segments}",
            color=LogColor.BLUE,
        )

        if self._latest_factor_value is not None:
            self.log.info(
                f"Factor {self._factor_id}: {self._latest_factor_value:.6f} "
                f"(min_signal {self._min_signal_magnitude:.3f})",
                color=LogColor.GREEN,
            )
        else:
            self.log.info(
                f"Factor {self._factor_id}: warming up...",
                color=LogColor.GREEN,
            )

        # -----------------------------------------------------

        # P&L information
        self.log.info("Portfolio -> P&L information:", color=LogColor.YELLOW)

        realized_pnl = self.portfolio.realized_pnl(self.config.instrument_id)
        self.log.info(f"Realized P&L: {realized_pnl}", color=LogColor.YELLOW)

        unrealized_pnl = self.portfolio.unrealized_pnl(self.config.instrument_id)
        self.log.info(f"Unrealized P&L: {unrealized_pnl}", color=LogColor.YELLOW)

        # -----------------------------------------------------

        self.log.info("Portfolio -> Account information:", color=LogColor.CYAN)
        margins_init = self.portfolio.margins_init(self.config.instrument_id.venue)
        self.log.info(f"Initial margin: {margins_init}", color=LogColor.CYAN)

        margins_maint = self.portfolio.margins_maint(self.config.instrument_id.venue)
        self.log.info(f"Maintenance margin: {margins_maint}", color=LogColor.CYAN)

        balances_locked = self.portfolio.balances_locked(self.config.instrument_id.venue)
        self.log.info(f"Locked balance: {balances_locked}", color=LogColor.CYAN)

    def get_strategy_summary(self) -> dict:
        """Get strategy performance summary with risk metrics."""
        current_exposure = self._get_current_notional_exposure() or 0.0

        # Get account info for risk metrics
        account = self.cache.account_for_venue(self.config.instrument_id.venue)
        if account:
            instrument = self.cache.instrument(self.config.instrument_id)
            if instrument:
                total_balance = account.balance_total(instrument.quote_currency)
                balance_used_pct = (current_exposure / float(total_balance)) * 100 if total_balance else 0.0
            else:
                balance_used_pct = 0.0
        else:
            balance_used_pct = 0.0

        active_segments = sum(1 for s in self._segment_states if s.has_inventory())
        frozen_segments = sum(
            1 for s in self._segment_states if s.frozen_until_ns > self._clock.timestamp_ns()
        )
        depleted_segments = sum(1 for s in self._segment_states if s.is_depleted)

        return {
            "instrument": str(self.config.instrument_id),
            "last_bar_close": self._last_bar_close,
            "current_exposure_usd": current_exposure,
            "balance_used_pct": balance_used_pct,
            "active_segments": active_segments,
            "frozen_segments": frozen_segments,
            "depleted_segments": depleted_segments,
            "factor": {
                "id": self._factor_id,
                "value": self._latest_factor_value,
                "min_signal": self._min_signal_magnitude,
                "required_history": self._warmup_bars,
                "indicator_ready": self._indicators_ready(),
            },
            "risk_config": {
                "max_account_usage_pct": float(self.config.max_account_usage_pct),
                "max_absolute_exposure": self.config.max_absolute_exposure,
                "position_risk_pct": float(self.config.position_risk_pct),
                "stop_loss_pct": self.config.stop_loss_pct,
            },
        }
    def on_order_filled(self, event: OrderFilled):
        """Handle fill reconciliation and basic position logging."""
        client_id = str(event.client_order_id)
        state = self._order_to_segment.get(client_id)
        if state is None:
            self.log.debug(f"OrderFilled {client_id} not mapped to segment")
            return

        self._apply_fill_to_segment(state, event)

        signed_fill = float(event.last_qty.as_decimal())
        if event.order_side == OrderSide.SELL:
            signed_fill *= -1

        pending_delta = self._order_pending_delta.get(client_id, 0.0)
        remaining = pending_delta - signed_fill

        if abs(remaining) <= self._min_order_size / 10:
            self._order_pending_delta.pop(client_id, None)
            self._order_to_segment.pop(client_id, None)
        else:
            self._order_pending_delta[client_id] = remaining

        if abs(state.pending_target_qty - state.current_qty) <= self._min_order_size:
            state.pending_target_qty = state.current_qty
            state.pending_timestamp_ns = 0

        self.log.debug(
            f"Seg{state.idx}: filled {signed_fill:+.6f} "
            f"current={state.current_qty:.6f} "
            f"pending_target={state.pending_target_qty:.6f}"
        )

    def on_position_opened(self, event: PositionOpened):
        """Log position open events."""
        self.log.info(f"Position opened: {event.position_id} qty={event.quantity}")

    def on_position_changed(self, event: PositionChanged):
        """Log position change events."""
        self.log.debug(f"Position changed: {event.position_id} qty={event.quantity}")

    def on_position_closed(self, event: PositionClosed):
        """Log position close events."""
        self.log.info(f"Position closed: {event.position_id}")
