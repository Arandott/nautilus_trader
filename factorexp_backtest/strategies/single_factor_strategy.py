"""
Single-factor trading strategy for backtesting.

This strategy runs ONE factor at a time, where the factor output
directly maps to position sizing under 2x leverage.

ARCHITECTURE: Uses 96 real Position objects in HEDGING OMS mode.
Each segment has its own PositionId (LONG/SHORT), tracked by SegmentState.
Portfolio automatically manages PnL and account balances.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from factorexp_backtest.configs.config_loader import FactorConfigLoader
from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.events import PositionChanged
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.events import PositionOpened
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


@dataclass
class SegmentState:
    """
    State tracking for a single segment (1/96 of total equity).

    Each segment has independent LONG and SHORT position IDs for HEDGING mode.
    Portfolio manages actual positions; this tracks targets and risk limits.

    CRITICAL EQUITY SEMANTICS:
    - current_equity: Cash + realized PnL ONLY (excludes unrealized PnL)
    - Use _get_segment_equity(state, price) to get TRUE equity (cash + unrealized)
    - peak_equity: High-water mark for trailing stop-loss (includes unrealized)

    When positions close, realized PnL is absorbed into current_equity.
    This ensures position sizing reflects actual available capital.
    """

    idx: int  # Segment index (0-95)
    long_id: PositionId  # Position ID for long positions
    short_id: PositionId  # Position ID for short positions

    # Equity tracking (REALIZED-ONLY, use _get_segment_equity for true equity)
    current_equity: float  # Cash + realized PnL (NOT including unrealized)
    initial_equity: float  # Original allocation baseline (never modified)
    peak_equity: float = 0.0  # High-water mark for trailing stop (includes unrealized)
    cumulative_realized_pnl: float = 0.0  # Total realized PnL since inception

    # Risk management
    max_leverage: float = 2.0  # Maximum leverage (from risk_config)
    stop_loss_pct: float = 0.05  # Stop loss percentage (from risk_config)
    frozen_until_ns: int = 0  # Freeze until timestamp (nanoseconds)

    # Capital depletion tracking
    is_depleted: bool = False  # Permanent death flag (equity <= 0)
    depletion_timestamp_ns: int = 0  # When segment was depleted

    # PER-SIDE position tracking (CRITICAL FIX for orphaned positions)
    # Instead of a single active_position_id that forgets the opposite side during flips,
    # we now explicitly track whether each side has open inventory
    has_open_long: bool = False  # True if LONG position has size > 0
    has_open_short: bool = False  # True if SHORT position has size > 0

    # Convenience fields (derived from has_open_long/has_open_short)
    # active_position_id: The "dominant" side's ID (whichever was opened most recently)
    # active_side: 'LONG' or 'SHORT' or None (for backwards compatibility with existing code)
    active_position_id: PositionId | None = None  # Dominant position ID (may not be the only open position!)
    active_side: str | None = None  # 'LONG' or 'SHORT' or None

    # Pending state (for event-driven updates)
    pending_target_qty: float = 0.0  # Target quantity from last rebalance
    pending_timestamp_ns: int = 0  # When the order was submitted

    @property
    def is_frozen(self) -> bool:
        """Check if segment is frozen (risk triggered) or depleted."""
        return self.frozen_until_ns > 0 or self.is_depleted

    @property
    def stop_loss_amt(self) -> float:
        """Maximum loss before forced liquidation (based on current equity)."""
        return self.current_equity * self.stop_loss_pct


class SingleFactorStrategyConfig(StrategyConfig):
    """
    Configuration for SingleFactorStrategy.

    Parameters
    ----------
    instrument_id : str
        The instrument ID for trading.
    bar_type : str
        The bar type specification for data.
    config_path : str
        Path to the factor configuration YAML file.
    factor_id : str
        The single factor ID to run (e.g., "amt_momentum").
    rebalance_interval : int, optional
        Bars between rebalances (default from config or 30).
    position_scale : float
        Scale factor for position sizing (1.0 = use factor value directly).
    order_id_tag : str
        Tag for segment position IDs (default: "FACTOREXP").
    """

    instrument_id: str = ""  # Must be provided
    bar_type: str = "BTCUSDT.BINANCE-15-MINUTE-LAST-EXTERNAL"
    config_path: str = "configs/factors.yaml"
    factor_id: str = "amt_momentum"
    rebalance_interval: int | None = None
    position_scale: float = 1.0
    order_id_tag: str = "FACTOREXP"  # Tag for HEDGING position IDs


class SingleFactorStrategy(Strategy):
    """
    A single-factor trading strategy.

    This strategy runs ONE factor where the output Clip(ZScore(...), -2, 2)
    directly maps to position sizing under 2x leverage.
    """

    def __init__(self, config: SingleFactorStrategyConfig):
        """Initialize the strategy with HEDGING OMS and 96 real positions."""
        super().__init__(config)

        # Configuration
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.factor_id = config.factor_id
        self.position_scale = Decimal(str(config.position_scale))
        self._order_id_tag = config.order_id_tag  # Store as private attribute

        # Load configuration
        config_path = Path(config.config_path)
        if not config_path.is_absolute():
            config_path = Path(__file__).parent.parent / config_path

        self.config_loader = FactorConfigLoader(config_path)
        self.factor_config = self.config_loader.get_factor(config.factor_id)
        self.risk_config = self.config_loader.risk_config
        self.execution_config = self.config_loader.execution_config

        # Get defaults
        defaults = self.config_loader.get_defaults()
        self.zscore_period = defaults.get("zscore_period", 5760)

        # State
        self.instrument: Instrument | None = None
        self.factor_indicator: FactorExpIndicator | None = None

        # Segment tracking (96 real positions in HEDGING mode)
        self.segment_count = 96
        self.segment_states: list[SegmentState] = []
        self.position_to_segment: dict[PositionId, SegmentState] = {}
        self.segment_index = 0  # Next segment to rebalance (rotation)
        self.last_price: float | None = None  # Last bar close for PnL tracking

        # Risk parameters (will be set in on_start from risk_config)
        self.max_leverage: float = 2.0
        self.stop_loss_pct: float = 0.05
        self.freeze_duration_bars: int = 96  # Default freeze duration
        self.bar_duration_ns: int = 0  # Bar duration in nanoseconds (set in on_start)

    def on_start(self):
        """Actions to be performed on strategy start."""
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument {self.instrument_id}")
            self.stop()  # Stop strategy gracefully - 以遵循规范为荣
            return

        # Check if factor requires extended bar support
        if self.factor_config.requires_extended:
            # Check support using feature flag approach - 以复用现有为荣
            try:
                from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS
                has_extended = bool(EXTENDED_BAR_FIELD_SPECS)
            except Exception:
                has_extended = False

            if not has_extended:
                self.log.error(
                    f"Factor '{self.factor_config.name}' requires extended bar support "
                    f"which is not available"
                )
                self.stop()
                return

        # Initialize the single factor indicator
        # Period is auto-detected from the expression tree
        self.factor_indicator = FactorExpIndicator(
            expression=self.factor_config.expression
        )

        # Register indicator for automatic updates - 以复用现有为荣
        self.register_indicator_for_bars(self.bar_type, self.factor_indicator)

        # Request historical data for warmup - CRITICAL!
        self.request_bars(self.bar_type)

        # Subscribe to live bar data
        self.subscribe_bars(self.bar_type)

        # Initialize segment states (96 real positions in HEDGING mode)
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        if account is None:
            self.log.error(f"Could not get account for venue {venue}")
            self.stop()
            return

        initial_equity = float(account.balance_total().as_decimal())

        # Extract risk parameters from config
        if self.risk_config:
            self.max_leverage = self.risk_config.max_position_size
            self.stop_loss_pct = self.risk_config.stop_loss
            if self.risk_config.max_rebalance_interval:
                self.freeze_duration_bars = self.risk_config.max_rebalance_interval

        # Create 96 SegmentState objects with unique PositionIds
        equity_per_segment = initial_equity / self.segment_count
        for idx in range(self.segment_count):
            # Create LONG and SHORT position IDs for this segment
            long_id = PositionId(
                f"{self.instrument_id}-{self._order_id_tag}-SEG{idx:02d}-LONG"
            )
            short_id = PositionId(
                f"{self.instrument_id}-{self._order_id_tag}-SEG{idx:02d}-SHORT"
            )

            # Create segment state with realized-only equity tracking
            state = SegmentState(
                idx=idx,
                long_id=long_id,
                short_id=short_id,
                current_equity=equity_per_segment,  # Cash + realized PnL (initial = cash only)
                initial_equity=equity_per_segment,  # Original allocation baseline
                peak_equity=equity_per_segment,  # Initialize high-water mark at starting equity
                max_leverage=self.max_leverage,
                stop_loss_pct=self.stop_loss_pct,
            )

            self.segment_states.append(state)
            # Map both LONG and SHORT IDs to this segment
            self.position_to_segment[long_id] = state
            self.position_to_segment[short_id] = state

        self.log.info(
            f"Initialized {self.segment_count} segments in HEDGING OMS mode",
            LogColor.GREEN,
        )
        self.log.info(
            f"Per-segment equity: {equity_per_segment:.2f} USDT, "
            f"max_leverage: {self.max_leverage}x, "
            f"stop_loss: {self.stop_loss_pct*100:.1f}%",
            LogColor.CYAN,
        )
        self.log.info(
            f"SingleFactorStrategy initialized with factor '{self.factor_config.name}'",
            LogColor.GREEN,
        )
        self.log.info(
            f"Expression: {self.factor_config.expression[:80]}...",
            LogColor.CYAN,
        )
        # Calculate bar duration in nanoseconds for freeze calculations
        # This makes freeze duration work correctly for any bar type (1min, 5min, 15min, 1hour, etc.)
        bar_spec = self.bar_type.spec

        # Import BarAggregation enum for comparison
        from nautilus_trader.model.enums import BarAggregation

        # Map aggregation to duration and display name
        if bar_spec.aggregation == BarAggregation.MINUTE:
            self.bar_duration_ns = bar_spec.step * 60 * 1_000_000_000
            agg_name = "minute"
        elif bar_spec.aggregation == BarAggregation.HOUR:
            self.bar_duration_ns = bar_spec.step * 60 * 60 * 1_000_000_000
            agg_name = "hour"
        elif bar_spec.aggregation == BarAggregation.SECOND:
            self.bar_duration_ns = bar_spec.step * 1_000_000_000
            agg_name = "second"
        else:
            # Fallback: assume 15 minutes for other aggregation types
            self.bar_duration_ns = 15 * 60 * 1_000_000_000
            agg_name = "unknown"
            self.log.warning(
                f"Unknown bar aggregation {bar_spec.aggregation}, "
                "defaulting to 15min for freeze calculations",
                LogColor.YELLOW,
            )

        self.log.info(
            f"Rebalance: Every {bar_spec.step} {agg_name}(s)",
            LogColor.CYAN,
        )

    # ========== CENTRALIZED INVENTORY ACCESS HELPERS ==========
    # These helpers ensure we always check BOTH sides (LONG and SHORT)
    # to prevent "orphaned positions" from escaping tracking

    def _get_position(self, position_id: PositionId):
        """
        Safely get a position from cache.

        Returns
        -------
        Position | None
            The position object, or None if not found or closed.
        """
        position = self.cache.position(position_id)
        if position is None or position.is_closed:
            return None
        return position

    def _get_both_positions(self, state: SegmentState) -> tuple:
        """
        Get BOTH LONG and SHORT positions for a segment.

        CRITICAL: This is the single source of truth for segment inventory.
        All position queries should use this function to prevent orphaned positions.

        Returns
        -------
        tuple[Position | None, Position | None]
            (long_position, short_position) - either or both may be None
        """
        long_pos = self._get_position(state.long_id)
        short_pos = self._get_position(state.short_id)
        return long_pos, short_pos

    def _get_net_position_qty(self, state: SegmentState) -> float:
        """
        Calculate NET position quantity across BOTH sides.

        CRITICAL FIX: This replaces the old _current_segment_qty which only
        looked at active_position_id and missed orphaned positions.

        Formula: net_qty = long_qty + short_qty (where short_qty is negative)

        Returns
        -------
        float
            Net signed quantity (positive for net long, negative for net short, 0 for flat)
        """
        long_pos, short_pos = self._get_both_positions(state)

        long_qty = float(long_pos.signed_qty) if long_pos else 0.0
        short_qty = float(short_pos.signed_qty) if short_pos else 0.0

        return long_qty + short_qty

    def _current_segment_qty(self, state: SegmentState) -> float:
        """
        Get current position quantity for a segment.

        DEPRECATED: Use _get_net_position_qty() instead.
        This function is kept for backwards compatibility but now delegates
        to the new helper that checks both sides.
        """
        return self._get_net_position_qty(state)

    def _log_segment_analytics(self):
        """
        Log segment health metrics for observability.

        CRITICAL: Uses TRUE equity (cash + unrealized) for accurate reporting.
        Called once per rotation cycle (every 96 bars) to track:
        - Active/frozen/depleted segment counts
        - Total equity and realized PnL across all segments
        - Worst-performing segments
        """
        # Count segments with open positions (using per-side flags)
        active = sum(1 for s in self.segment_states if s.has_open_long or s.has_open_short)
        frozen = sum(
            1 for s in self.segment_states
            if s.frozen_until_ns > self.clock.timestamp_ns() and not s.is_depleted
        )
        depleted = sum(1 for s in self.segment_states if s.is_depleted)

        # Calculate TRUE total equity (cash + unrealized) using last known price
        # Fallback to current_equity if no price available yet
        if hasattr(self, 'last_price') and self.last_price is not None:
            # last_price is already a Price object from bar.close
            price_obj = self.last_price
            total_equity = sum(
                self._get_segment_equity(s, price_obj) for s in self.segment_states
            )
            # Find worst-performing segment by TRUE equity
            worst_segment = min(
                self.segment_states,
                key=lambda s: self._get_segment_equity(s, price_obj)
            )
            worst_equity = self._get_segment_equity(worst_segment, price_obj)
        else:
            # Fallback: use cash-only equity if no price available yet
            total_equity = sum(s.current_equity for s in self.segment_states)
            worst_segment = min(self.segment_states, key=lambda s: s.current_equity)
            worst_equity = worst_segment.current_equity

        total_realized_pnl = sum(s.cumulative_realized_pnl for s in self.segment_states)
        initial_total_equity = sum(s.initial_equity for s in self.segment_states)
        worst_pnl = worst_equity - worst_segment.initial_equity

        self.log.info(
            f"Segment Health: active={active}, frozen={frozen}, depleted={depleted} | "
            f"total_equity={total_equity:.2f} (init={initial_total_equity:.2f}) | "
            f"realized_pnl={total_realized_pnl:.2f} | "
            f"worst_seg={worst_segment.idx} (pnl={worst_pnl:.2f})",
            LogColor.CYAN,
        )

    def _get_segment_equity(self, state: SegmentState, price_obj) -> float:
        """
        Calculate TRUE segment equity (cash + realized + unrealized PnL).

        CRITICAL FIX: Now checks BOTH LONG and SHORT positions to capture
        unrealized PnL from ALL open positions, not just active_position_id.

        CRITICAL EQUITY SEMANTICS:
        - state.current_equity: Cash + realized PnL ONLY (excludes unrealized)
        - This function returns: Cash + realized + unrealized PnL (TRUE equity)

        Formula: TRUE equity = current_equity + unrealized_pnl_long + unrealized_pnl_short

        This is the only correct equity measure for:
        - Stop-loss checking (must include all losses)
        - Position sizing (must reflect true available capital)
        - Performance reporting (must show real P&L)

        When flat (no positions on either side), unrealized PnL = 0, so TRUE equity = current_equity.
        """
        # Start with cash + realized PnL
        equity = state.current_equity

        # CRITICAL FIX: Add unrealized PnL from BOTH sides
        long_pos, short_pos = self._get_both_positions(state)

        if long_pos is not None:
            unrealized_long = float(long_pos.unrealized_pnl(price_obj).as_decimal())
            equity += unrealized_long

        if short_pos is not None:
            unrealized_short = float(short_pos.unrealized_pnl(price_obj).as_decimal())
            equity += unrealized_short

        return equity

    def on_bar(self, bar: Bar):
        """
        Handle bar data update.

        CRITICAL: Every bar must:
        1. Check ALL 96 segments for risk (stop loss, equity depletion)
        2. Check account-level health (total equity > 0)
        3. Rebalance ONE segment (rotation)
        """
        # Update factor indicator
        if self.factor_indicator:
            self.factor_indicator.handle_bar(bar)

        # Track last price as Price object (needed for unrealized_pnl calculations)
        self.last_price = bar.close

        # Check if indicator is ready
        if not self.factor_indicator or not self.factor_indicator.initialized:
            self.log.debug("Factor indicator warming up...")
            return

        current_price = float(bar.close)
        price_obj = self.instrument.make_price(Decimal(str(current_price)))

        # PHASE 1: Check account-level health BEFORE any operations
        venue = self.instrument_id.venue
        account = self.portfolio.account(venue)
        if account is None:
            self.log.error("Cannot get account, skipping bar")
            return

        # CRITICAL: Calculate TRUE account equity including unrealized PnL
        # account.balance_total() only returns cash, NOT including open positions!
        cash_balance = float(account.balance_total().as_decimal())

        # Calculate total unrealized PnL from ALL positions
        # CRITICAL FIX: Must check BOTH sides (LONG and SHORT) to capture ALL unrealized PnL
        # Previous code only checked active_position_id, missing orphaned positions
        total_unrealized_pnl = 0.0
        active_segments = 0
        for segment_state in self.segment_states:
            # Check if segment has ANY open inventory (using per-side flags)
            has_inventory = segment_state.has_open_long or segment_state.has_open_short

            if has_inventory:
                active_segments += 1

                # Get BOTH positions and sum their unrealized PnL
                long_pos, short_pos = self._get_both_positions(segment_state)

                if long_pos is not None:
                    unrealized_long = float(long_pos.unrealized_pnl(price_obj).as_decimal())
                    total_unrealized_pnl += unrealized_long

                if short_pos is not None:
                    unrealized_short = float(short_pos.unrealized_pnl(price_obj).as_decimal())
                    total_unrealized_pnl += unrealized_short

        # TRUE equity = cash + unrealized PnL
        total_equity = cash_balance + total_unrealized_pnl
        # Log the amount of total equity at debug level to avoid noise in long runs
        self.log.debug(f"Total Equity: {total_equity:.2f} USDT")

        # Log analytics every 96 bars (once per rotation cycle)
        if self.segment_index == 0:
            self.log.info(
                f"Account Health: cash={cash_balance:.2f}, "
                f"unrealized={total_unrealized_pnl:.2f}, "
                f"equity={total_equity:.2f}, "
                f"active_segs={active_segments}/96",
                LogColor.CYAN,
            )
            # Log detailed segment analytics
            self._log_segment_analytics()

        # CRITICAL: If account is liquidated (total equity <= 0), STOP ALL TRADING
        if total_equity <= 0:
            self.log.error(
                f"ACCOUNT LIQUIDATED: cash={cash_balance:.2f}, "
                f"unrealized_pnl={total_unrealized_pnl:.2f}, "
                f"total_equity={total_equity:.2f} <= 0, STOPPING STRATEGY",
                LogColor.RED,
            )
            self.stop()
            return

        # WARNING: If account equity is critically low (< 10% of initial)
        initial_equity = self.segment_count * self.segment_states[0].initial_equity
        if total_equity < initial_equity * 0.1:
            self.log.warning(
                f"CRITICAL: Account equity={total_equity:.2f} < 10% of initial={initial_equity:.2f} "
                f"(cash={cash_balance:.2f}, unrealized={total_unrealized_pnl:.2f})",
                LogColor.RED,
            )

        # PHASE 2: Check risk for ALL 96 segments (not just current one!)
        # This prevents undetected losses accumulating in non-rotated segments
        #
        # CRITICAL FIX: Now uses per-side flags (has_open_long/short) instead of active_position_id
        # This ensures ALL segments with inventory get risk-checked, eliminating orphaned positions
        segments_closed = 0

        for segment_state in self.segment_states:
            # Check if segment has ANY open inventory (using per-side flags)
            has_inventory = segment_state.has_open_long or segment_state.has_open_short

            if has_inventory:
                # Run risk check on this segment
                if self._check_segment_risk(segment_state, price_obj):
                    segments_closed += 1

        if segments_closed > 0:
            self.log.warning(
                f"Risk check: Force closed {segments_closed} segments this bar",
                LogColor.YELLOW,
            )

        # PHASE 3: Rebalance current segment (rotation as usual)
        state = self.segment_states[self.segment_index]
        self._rebalance_segment(state, bar)

        # Rotate to next segment
        self.segment_index = (self.segment_index + 1) % self.segment_count

    def _rebalance_segment(self, state: SegmentState, bar: Bar):
        """
        Rebalance a single segment using Portfolio-managed positions.

        ENHANCED: Now properly handles segment depletion and extended freezes
        for equity-triggered events.

        This is the core rebalancing logic per segment:
        1. Skip depleted segments (permanent death)
        2. Check freeze state and unfreeze if time elapsed
        3. Check risk limits before trading
        4. Calculate target position using factor value
        5. Submit order if needed
        """
        # SKIP DEPLETED SEGMENTS: Permanently disabled when equity <= 0
        if state.is_depleted:
            return

        current_price = float(bar.close)
        price_obj = self.instrument.make_price(Decimal(str(current_price)))
        current_time_ns = self.clock.timestamp_ns()

        # Check freeze state (risk triggered)
        if state.frozen_until_ns and current_time_ns >= state.frozen_until_ns:
            state.frozen_until_ns = 0
            self.log.info(
                f"Seg{state.idx}: Unfreeze | equity={state.current_equity:.2f}",
                LogColor.GREEN,
            )

        if state.frozen_until_ns > current_time_ns:
            return  # Still frozen, skip rebalancing

        # Check risk before rebalancing
        if self._check_segment_risk(state, price_obj):
            return  # Risk triggered, segment frozen

        # Get TRUE equity (cash + unrealized) for position sizing
        segment_equity = self._get_segment_equity(state, price_obj)

        # ENHANCED: Depletion protection with extended freeze
        if segment_equity <= 0:
            self.log.error(
                f"Seg{state.idx}: Non-positive equity {segment_equity:.2f}, "
                f"forcing flat and freezing",
                LogColor.RED,
            )
            self._force_flat(state)

            # Freeze for 4x normal duration when equity-triggered
            # This prevents immediate re-entry after capital depletion
            state.frozen_until_ns = current_time_ns + (
                self.freeze_duration_bars * 4 * self.bar_duration_ns
            )
            return

        # Get factor value
        factor_value = self.factor_indicator.value
        if not -2 <= factor_value <= 2:
            self.log.error(f"Factor value {factor_value} outside expected range [-2, 2]")
            return

        # Calculate target
        target_weight = factor_value * float(self.position_scale)
        target_notional = target_weight * segment_equity

        # Apply risk limits
        max_notional = abs(segment_equity) * state.max_leverage
        if abs(target_notional) > max_notional:
            target_notional = max_notional * (1 if target_notional > 0 else -1)

        target_qty = target_notional / current_price
        current_qty = self._current_segment_qty(state)

        # Check minimum order size
        min_order = self.execution_config.min_order_size if self.execution_config else 0.001
        if abs(target_qty - current_qty) < min_order:
            self.log.debug(
                f"Seg{state.idx}: delta {abs(target_qty - current_qty):.6f} < min {min_order}, skipping"
            )
            return

        # Update peak equity if TRUE equity exceeds previous peak (trailing stop)
        if segment_equity > state.peak_equity:
            state.peak_equity = segment_equity
            self.log.debug(
                f"Seg{state.idx}: Peak equity updated to {state.peak_equity:.2f} (true equity)"
            )

        # Submit order
        self.log.info(
            f"Seg{state.idx}: factor={factor_value:.4f} | "
            f"eq={segment_equity:.2f} | "
            f"cur={current_qty:.6f} → target={target_qty:.6f}",
            LogColor.BLUE,
        )

        self._submit_segment_order(state, target_qty, current_qty)

        # Update pending state
        state.pending_target_qty = target_qty
        state.pending_timestamp_ns = current_time_ns

    def _submit_segment_order(self, state: SegmentState, target_qty: float, current_qty: float):
        """
        Submit order for a segment with correct position_id (HEDGING mode).

        CRITICAL FIX: Now closes ALL opposite-side inventory BEFORE opening new positions.
        This prevents residual positions from becoming orphaned during flips.

        Steps:
        1. Check BOTH sides for inventory that conflicts with target
        2. Close ALL conflicting inventory with reduce-only orders
        3. Only then open/adjust the target side position
        """
        min_order = self.execution_config.min_order_size if self.execution_config else 0.001

        # Determine target side
        target_side = "LONG" if target_qty > 0 else "SHORT" if target_qty < 0 else None

        # CRITICAL FIX: Get actual inventory from BOTH sides
        long_pos, short_pos = self._get_both_positions(state)
        long_qty = float(long_pos.signed_qty) if long_pos else 0.0
        short_qty = float(short_pos.signed_qty) if short_pos else 0.0

        # Step 1: Close ALL opposite-side inventory
        positions_to_close = []

        if target_side == "LONG" and short_pos is not None:
            # Target is LONG, close any SHORT inventory
            positions_to_close.append(('SHORT', state.short_id, short_pos, short_qty))
        elif target_side == "SHORT" and long_pos is not None:
            # Target is SHORT, close any LONG inventory
            positions_to_close.append(('LONG', state.long_id, long_pos, long_qty))
        elif target_side is None:
            # Target is FLAT, close BOTH sides
            if long_pos is not None:
                positions_to_close.append(('LONG', state.long_id, long_pos, long_qty))
            if short_pos is not None:
                positions_to_close.append(('SHORT', state.short_id, short_pos, short_qty))

        # Execute close orders for all conflicting inventory
        for side_name, position_id, position, qty in positions_to_close:
            close_qty = abs(qty)
            if close_qty >= min_order:
                close_order_qty = self.instrument.make_qty(Decimal(str(close_qty)))
                close_side = OrderSide.SELL if qty > 0 else OrderSide.BUY

                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=close_side,
                    quantity=close_order_qty,
                    reduce_only=True,
                )

                self.submit_order(close_order, position_id=position_id)

                self.log.info(
                    f"Seg{state.idx}: Closing opposite {side_name} position: qty={close_qty:.6f}",
                    LogColor.YELLOW,
                )

        # Step 2: If target is flat, we're done after closing
        if target_side is None:
            self.log.debug(f"Seg{state.idx}: Target is flat, done after closing opposite sides")
            return

        # Step 3: Calculate delta for the target side
        # After closing opposite side, only same-side inventory remains
        current_target_side_qty = long_qty if target_side == "LONG" else short_qty
        delta_qty = target_qty - current_target_side_qty

        # Step 4: Submit adjustment order for target side if needed
        if abs(delta_qty) >= min_order:
            order_qty = abs(delta_qty)
            order_qty_obj = self.instrument.make_qty(Decimal(str(order_qty)))

            # Determine order side based on delta direction
            order_side = OrderSide.BUY if delta_qty > 0 else OrderSide.SELL

            # Determine which position_id to use (based on target side)
            position_id = state.long_id if target_side == "LONG" else state.short_id

            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=order_side,
                quantity=order_qty_obj,
            )

            # Submit with position_id for HEDGING mode
            self.submit_order(order, position_id=position_id)

            self.log.info(
                f"Seg{state.idx}: Adjusting {target_side} position: "
                f"delta={delta_qty:+.6f} (current={current_target_side_qty:.6f} → target={target_qty:.6f})",
                LogColor.GREEN if delta_qty > 0 else LogColor.RED,
            )

    def on_position_opened(self, event: PositionOpened):
        """
        Handle position opened event.

        CRITICAL FIXES:
        1. Framework passes PositionOpened event, not Position object
        2. Now sets per-side flags (has_open_long/has_open_short) to prevent orphaned positions
        """
        # Check if this position belongs to our strategy
        if event.position_id not in self.position_to_segment:
            return

        # Fetch the actual Position object from cache
        position = self.cache.position(event.position_id)
        if position is None:
            self.log.warning(f"Position {event.position_id} not found in cache")
            return

        state = self.position_to_segment[event.position_id]

        # CRITICAL FIX: Set per-side flag based on which position ID was opened
        is_long = (event.position_id == state.long_id)
        is_short = (event.position_id == state.short_id)

        if is_long:
            state.has_open_long = True
            state.active_side = "LONG"
        elif is_short:
            state.has_open_short = True
            state.active_side = "SHORT"

        # Update active_position_id to the most recently opened side
        state.active_position_id = event.position_id

        self.log.info(
            f"Seg{state.idx}: Position opened - {state.active_side} {float(position.signed_qty):.6f} | "
            f"has_open: LONG={state.has_open_long}, SHORT={state.has_open_short}",
            LogColor.GREEN
        )

    def on_position_changed(self, event: PositionChanged):
        """
        Handle position changed event.

        CRITICAL FIX: Framework passes PositionChanged event, not Position object.
        event.id is the event UUID, event.position_id is the actual position identifier.
        """
        # Check if this position belongs to our strategy
        if event.position_id not in self.position_to_segment:
            return

        # Fetch the actual Position object from cache
        position = self.cache.position(event.position_id)
        if position is None:
            return

        state = self.position_to_segment[event.position_id]

        self.log.debug(
            f"Seg{state.idx}: Position changed - {state.active_side} {float(position.signed_qty):.6f}, "
            f"realized_pnl={float(position.realized_pnl.as_decimal()):.2f}"
        )

    def on_position_closed(self, event: PositionClosed):
        """
        Handle position closed event.

        CRITICAL FIXES:
        1. Framework passes PositionClosed event, not Position object.
           event.id is the event UUID, event.position_id is the actual position identifier.
        2. Mark-to-market the segment equity by absorbing realized PnL.
        3. Only clear active_position_id if the closed position is the currently active one.
        """
        # Check if this position belongs to our strategy
        if event.position_id not in self.position_to_segment:
            return

        # Fetch the actual Position object from cache
        position = self.cache.position(event.position_id)
        if position is None:
            self.log.warning(f"Position {event.position_id} not found in cache")
            return

        state = self.position_to_segment[event.position_id]

        # Extract realized PnL from this position
        realized_pnl = float(position.realized_pnl.as_decimal())

        # Store equity before update for logging
        equity_before = state.current_equity

        # Update segment's working capital with realized PnL
        state.current_equity += realized_pnl
        state.cumulative_realized_pnl += realized_pnl

        # CRITICAL FIX: Clear per-side flag based on which position closed
        is_long = (event.position_id == state.long_id)
        is_short = (event.position_id == state.short_id)

        if is_long:
            state.has_open_long = False
        elif is_short:
            state.has_open_short = False

        self.log.info(
            f"Seg{state.idx}: Position closed - {event.position_id} | "
            f"realized_pnl={realized_pnl:.2f} | "
            f"equity: {equity_before:.2f} → {state.current_equity:.2f} | "
            f"has_open: LONG={state.has_open_long}, SHORT={state.has_open_short}",
            LogColor.CYAN,
        )

        # Update peak equity if segment is now FULLY flat (no positions on either side)
        # This ensures trailing stop baseline advances when positions are closed profitably
        if not state.has_open_long and not state.has_open_short:
            # Segment is completely flat, so cash equity = true equity
            if state.current_equity > state.peak_equity:
                state.peak_equity = state.current_equity
                self.log.debug(
                    f"Seg{state.idx}: Peak equity updated to {state.peak_equity:.2f} (segment flat)"
                )

        # Check for capital depletion
        if state.current_equity <= 0:
            state.is_depleted = True
            state.depletion_timestamp_ns = self.clock.timestamp_ns()
            self.log.error(
                f"Seg{state.idx}: DEPLETED | "
                f"equity={state.current_equity:.2f} <= 0, segment permanently disabled",
                LogColor.RED,
            )

        # Update active_position_id pointer
        # If the closed position was the active one, switch pointer to the other side if it exists
        if event.position_id == state.active_position_id:
            if state.has_open_long:
                # Switch to LONG side
                state.active_position_id = state.long_id
                state.active_side = "LONG"
                self.log.debug(f"Seg{state.idx}: Switched active tracking to LONG side")
            elif state.has_open_short:
                # Switch to SHORT side
                state.active_position_id = state.short_id
                state.active_side = "SHORT"
                self.log.debug(f"Seg{state.idx}: Switched active tracking to SHORT side")
            else:
                # Both sides closed
                state.active_position_id = None
                state.active_side = None
                self.log.debug(f"Seg{state.idx}: Cleared active position tracking (fully flat)")
        else:
            self.log.debug(
                f"Seg{state.idx}: Closed {event.position_id} but active is {state.active_position_id}, "
                "keeping active pointer intact"
            )

    def _check_segment_risk(self, state: SegmentState, price_obj) -> bool:
        """
        Check segment risk using TRAILING STOP-LOSS based on peak equity.

        CRITICAL FIX: Previous implementation used equity_drawdown = current_equity - total_equity,
        which only captured NEW unrealized losses. Historical realized losses were ignored,
        allowing segments to lose 90% of capital via realized PnL without triggering stop-loss.

        NEW LOGIC:
        - Baseline: state.peak_equity (high-water mark including unrealized PnL)
        - Drawdown: peak_equity - total_equity (captures ALL losses, realized + unrealized)
        - Threshold: peak_equity * stop_loss_pct

        This ensures stop-loss triggers when total losses exceed threshold, regardless
        of whether losses are realized or unrealized.

        Returns True if risk triggered (segment frozen/force-flattened).
        """
        # Skip depleted segments (already dead)
        if state.is_depleted:
            return False

        # Calculate total equity including unrealized PnL (TRUE equity)
        total_equity = self._get_segment_equity(state, price_obj)

        # DEFENSIVE: Update peak equity if current equity exceeds it
        # Primary updates happen in _rebalance_segment (line 573) and on_position_closed (line 765),
        # but this ensures peak_equity never lags behind reality (e.g., if rebalance was skipped due to freeze)
        # This check BEFORE drawdown calculation ensures we don't trigger false positives
        if total_equity > state.peak_equity:
            old_peak = state.peak_equity
            state.peak_equity = total_equity
            self.log.debug(
                f"Seg{state.idx}: Peak equity updated {old_peak:.2f} → {total_equity:.2f} (defensive check)"
            )

        # TRAILING STOP-LOSS: Measure drawdown from peak equity
        # This captures ALL losses (realized + unrealized) from the high-water mark
        baseline = state.peak_equity  # Could also use initial_equity for hard stop
        drawdown = baseline - total_equity
        threshold = baseline * state.stop_loss_pct

        self.log.debug(
            f"Seg{state.idx}: Risk check | peak={state.peak_equity:.2f}, "
            f"total_equity={total_equity:.2f}, drawdown={drawdown:.2f}, "
            f"threshold={threshold:.2f}"
        )

        # Trigger stop-loss if drawdown exceeds threshold
        if drawdown > threshold:
            self.log.warning(
                f"Seg{state.idx}: STOP LOSS TRIGGERED | "
                f"drawdown={drawdown:.2f} > threshold={threshold:.2f} | "
                f"peak={baseline:.2f}, current={total_equity:.2f}, "
                f"loss_pct={drawdown/baseline*100:.2f}%",
                LogColor.RED,
            )

            # Force flat and freeze segment
            self._force_flat(state)
            state.frozen_until_ns = self.clock.timestamp_ns() + (
                self.freeze_duration_bars * self.bar_duration_ns
            )

            # CRITICAL FIX: Reset peak_equity to current level after stop-loss
            # Without this, segment will immediately re-trigger stop-loss when unfrozen
            # because drawdown = old_peak - current_equity still exceeds threshold
            state.peak_equity = max(total_equity, state.current_equity)

            # Clear pending orders to prevent stale rebalance targets
            state.pending_target_qty = 0.0
            state.pending_timestamp_ns = 0

            self.log.info(
                f"Seg{state.idx}: Peak equity reset to {state.peak_equity:.2f} after stop-loss",
                LogColor.YELLOW,
            )

            return True

        # TOTAL EQUITY DEPLETION CHECK
        if total_equity <= 0:
            self.log.error(
                f"Seg{state.idx}: EQUITY DEPLETED | "
                f"total_equity={total_equity:.2f} <= 0, forcing flat and marking depleted",
                LogColor.RED,
            )

            self._force_flat(state)

            # Reset peak_equity to prevent infinite loop (though segment will be depleted soon)
            state.peak_equity = max(total_equity, state.current_equity)
            state.pending_target_qty = 0.0
            state.pending_timestamp_ns = 0
            # Will be marked depleted when position closes in on_position_closed()

            return True

        return False

    def _force_flat(self, state: SegmentState):
        """
        Force segment to flat position by closing ALL open positions.

        CRITICAL FIX: Now iterates BOTH sides (LONG and SHORT) and closes any
        open inventory, regardless of which side active_position_id points to.
        This prevents orphaned positions from escaping liquidation.
        """
        min_order = self.execution_config.min_order_size if self.execution_config else 0.001

        # Get both positions
        long_pos, short_pos = self._get_both_positions(state)

        positions_to_close = []
        if long_pos is not None:
            positions_to_close.append(('LONG', state.long_id, long_pos))
        if short_pos is not None:
            positions_to_close.append(('SHORT', state.short_id, short_pos))

        if not positions_to_close:
            self.log.debug(f"Seg{state.idx}: _force_flat called but no positions to close")
            return

        self.log.warning(
            f"Seg{state.idx}: _force_flat closing {len(positions_to_close)} position(s): "
            f"LONG={long_pos is not None}, SHORT={short_pos is not None}",
            LogColor.RED,
        )

        # Close all open positions on both sides
        for side_name, position_id, position in positions_to_close:
            close_qty = abs(float(position.signed_qty))

            if close_qty >= min_order:
                close_order_qty = self.instrument.make_qty(Decimal(str(close_qty)))
                close_side = OrderSide.SELL if position.signed_qty > 0 else OrderSide.BUY

                close_order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=close_side,
                    quantity=close_order_qty,
                    reduce_only=True,
                )

                self.submit_order(close_order, position_id=position_id)

                self.log.warning(
                    f"Seg{state.idx}: Forcing flat - closing {side_name} position "
                    f"qty={close_qty:.6f}, unrealized_pnl={float(position.unrealized_pnl(self.last_price).as_decimal()):.2f}",
                    LogColor.RED,
                )
            else:
                self.log.warning(
                    f"Seg{state.idx}: {side_name} position qty={close_qty:.6f} below min_order={min_order}, skipping",
                    LogColor.YELLOW,
                )

        # Note: per-side flags (has_open_long/short) and active_position_id will be
        # cleared by on_position_closed() when the close orders execute

    def on_stop(self):
        """Actions to be performed on strategy stop."""
        # Cancel all orders and close all positions
        self.cancel_all_orders(self.instrument_id)
        self.close_all_positions(self.instrument_id)

        # Unsubscribe from data
        self.unsubscribe_bars(self.bar_type)

        # Log final state - use per-side flags for accurate counting
        total_positions = sum(
            1 for s in self.segment_states if s.has_open_long or s.has_open_short
        )
        self.log.info(
            f"Strategy stopped | Active segments: {total_positions}/{self.segment_count}",
            LogColor.RED,
        )

    def on_reset(self):
        """Actions to be performed on strategy reset."""
        # Reset indicator
        if self.factor_indicator:
            self.factor_indicator.reset()

        # Reset segment states
        for state in self.segment_states:
            state.active_position_id = None
            state.active_side = None
            state.pending_target_qty = 0.0
            state.pending_timestamp_ns = 0
            state.frozen_until_ns = 0

        # Reset rotation index
        self.segment_index = 0
        self.last_price = None

        self.log.info("Strategy reset")
