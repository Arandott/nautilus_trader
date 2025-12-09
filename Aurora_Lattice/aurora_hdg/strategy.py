"""Aurora HF Dynamic Grid strategy implementation."""

from __future__ import annotations

import math
from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.message import Event
from nautilus_trader.core.nautilus_pyo3.indicators import BookL1Factors, BookMidPriceVolEstimator
from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide, BookType, OrderSide, PositionSide, TimeInForce
from nautilus_trader.model.events import PositionChanged, PositionClosed, PositionOpened
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import LimitOrder, MarketOrder
from nautilus_trader.trading.strategy import Strategy

from .config import AuroraHDGConfig
from .fill import QueueStats
from .position_risk import PositionRiskMonitor, calc_mo_slippage_price


class AuroraHdgStrategy(Strategy):
    """HF Dynamic Grid strategy built on Nautilus."""

    def __init__(self, config: AuroraHDGConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._book_type = BookType.L2_MBP
        self._pyo3_instrument_id = nautilus_pyo3.InstrumentId.from_str(self.config.instrument_id.value)
        self._pyo3_book_type = nautilus_pyo3.BookType(self._book_type.name)
        self._book = nautilus_pyo3.OrderBook(self._pyo3_instrument_id, self._pyo3_book_type)
        self._book_factors = BookL1Factors()
        self._vol = BookMidPriceVolEstimator()
        self._alpha_engine: aurora_bindings.AlphaEngine | None = None
        self._queue_stats = {
            OrderSide.BUY: QueueStats(lambda_mo=2.0, lambda_cancel=1.0, mean_mo=1.0, var_mo=1.0),
            OrderSide.SELL: QueueStats(lambda_mo=2.0, lambda_cancel=1.0, mean_mo=1.0, var_mo=1.0),
        }
        self._queue_window_s = max(config.fill_model.lambda_window_ms, 1) / 1000.0
        regime_params = aurora_bindings.AuroraRegimeParams(
            alpha_gate_bps=config.regime.alpha_gate_bps,
            trend_delta_ratio_threshold=config.regime.trend_delta_ratio_threshold,
            mo_imbalance_threshold=config.regime.mo_imbalance_threshold,
            hysteresis_ms=config.regime.hysteresis_ms,
            trend_opposite_clip_levels=config.regime.trend_opposite_clip_levels,
            trend_widen_mult=config.regime.trend_widen_mult,
            trend_reduce_levels=config.regime.trend_reduce_levels,
            chaos_widen_mult=config.regime.chaos_widen_mult,
            chaos_reduce_levels=config.regime.chaos_reduce_levels,
            pause_on_chaos=config.regime.pause_on_chaos,
        )
        self._risk = aurora_bindings.AuroraRiskAdvisor(
            vol_shock_sigma_mult=config.risk.shock_mode_sigma_mult,
            inventory_soft_limit=config.inventory.i_soft,
            hedge_cooldown_ms=config.risk.hedge_cooldown_ms,
            hedge_min_qty=config.risk.hedge_min_qty,
            regime_params=regime_params,
            mode=config.risk.mode,
        )
        self._pos_risk = PositionRiskMonitor(config.position_risk, config.taker, config.inventory.i_max)
        self._grid_planner = None
        self._inventory_qty: float = 0.0
        self._last_snapshot: dict | None = None  # stores scalar L1 values
        self._last_snapshot_ts: int = 0
        self._base_sigma: float = 1e-6
        # Will be set to the instrument price increment on start.
        self._tick_size: float = float(config.tick_size)
        self._tau_alpha_s: float = self.config.alpha.tau_ms / 1000.0
        self._tau_fill_s: float = self.config.fill_model.tau_ms / 1000.0
        self._order_ttl_ms: float = self.config.fill_model.ttl_ratio * self.config.fill_model.tau_ms
        self._last_refresh_ns: int = 0
        self._current_center: float | None = None
        self._last_trade_ts: int | None = None
        self._last_risk_state: aurora_bindings.AuroraRiskState | None = None
        self._last_regime: aurora_bindings.AuroraRegime | None = None

    # --- lifecycle ---

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.config.instrument_id} missing")
            self.stop()
            return

        # Always use the instrument-defined tick size to align pricing.
        self._tick_size = self.instrument.price_increment.as_double()
        self.log.info(
            f"Using instrument tick_size={self._tick_size:.8f}",
            LogColor.YELLOW,
        )

        self._grid_planner = self._build_grid_planner()
        self._book.reset()
        self._book_factors.reset()
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
        self.subscribe_order_book_deltas(
            self.config.instrument_id,
            self._book_type,
            managed=False,
            pyo3_conversion=True,
        )
        self.subscribe_trade_ticks(self.config.instrument_id)
        self.log.info(
            f"Aurora HDG started for instrument {self.config.instrument_id}",
            LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.log.info(f"Aurora HDG stopped", LogColor.YELLOW)

    # --- data handlers ---

    def on_order_book_deltas(self, deltas: nautilus_pyo3.OrderBookDeltas) -> None:
        if deltas.instrument_id.value != self.config.instrument_id.value:
            return
        self._book.apply_deltas(deltas)
        self._book_factors.handle_book(self._book)
        if not self._book_factors.has_market:
            return
        snapshot = self._book_factors
        fields = (
            snapshot.bid_price,
            snapshot.ask_price,
            snapshot.bid_qty,
            snapshot.ask_qty,
            snapshot.mid,
            snapshot.microprice,
            snapshot.imbalance,
        )
        if None in fields:
            return
        snapshot_values = {
            "bid": float(snapshot.bid_price),
            "ask": float(snapshot.ask_price),
            "bid_qty": float(snapshot.bid_qty),
            "ask_qty": float(snapshot.ask_qty),
            "mid": float(snapshot.mid),
            "microprice": float(snapshot.microprice),
            "imbalance": float(snapshot.imbalance),
        }
        self._process_snapshot(snapshot_values, deltas.ts_event, deltas)

    def on_trade_tick(self, tick: TradeTick) -> None:
        if tick.instrument_id != self.config.instrument_id:
            return
        qty = tick.size.as_double()
        dt = 1e-3
        if self._last_trade_ts:
            dt = max((tick.ts_event - self._last_trade_ts) / 1e9, 1e-3)
        self._last_trade_ts = tick.ts_event
        lam = qty / dt
        aggr_side = tick.aggressor_side
        if aggr_side == AggressorSide.BUYER:
            side = OrderSide.SELL
        elif aggr_side == AggressorSide.SELLER:
            side = OrderSide.BUY
        else:
            return  # Ignore ticks with no aggressor to avoid misclassifying flow
        stats = self._queue_stats[side]
        decay = self._queue_decay(dt)
        stats.update(mo_rate=lam, cxl_rate=lam * 0.3, mean_mo=qty, var_mo=max(qty**2, 1.0), decay=decay)
        self.log.debug(
            f"Trade tick processed side={side.name} qty={qty:.4f} "
            f"lam={lam:.4f} decay={decay:.4f}",
        )

    def on_event(self, event: Event) -> None:
        if isinstance(event, (PositionOpened, PositionChanged)):
            if event.instrument_id == self.config.instrument_id:
                qty = event.quantity.as_double()
                if event.side == PositionSide.SHORT:
                    qty = -qty
                prev_qty = self._inventory_qty
                self._inventory_qty = qty
                self.log.info(
                    f"Inventory updated via position event prev={prev_qty:.4f} "
                    f"now={self._inventory_qty:.4f}",
                )
        elif isinstance(event, PositionClosed):
            if event.instrument_id == self.config.instrument_id:
                self._inventory_qty = 0.0
                self.log.info(f"Inventory reset to flat after position close")

    # --- core logic ---

    def _process_snapshot(self, snapshot: dict, ts_ns: int, deltas: nautilus_pyo3.OrderBookDeltas) -> None:
        mid = snapshot["mid"]
        bid_qty = snapshot["bid_qty"]
        ask_qty = snapshot["ask_qty"]

        self._vol.update(mid)
        sigma_px = max(self._vol.sigma_px(mid), self._tick_size)
        self._base_sigma = 0.995 * self._base_sigma + 0.005 * self._vol.sigma_rel
        alpha_bps = 0.0
        if self._alpha_engine is not None:
            try:
                alpha_bps = self._alpha_engine.handle_order_book(ts_ns, deltas, self._inventory_qty)
            except Exception as exc:  # noqa: BLE001
                self.log.error(f"AlphaEngine handle_order_book failed: {exc}")
        self._update_queue_from_snapshot(snapshot, ts_ns, bid_qty, ask_qty)

        base_delta = self._base_delta(sigma_px, mid)
        delta_ratio = self._delta_ratio(base_delta)
        mo_imbalance = self._mo_imbalance()

        decision = self._risk.advise(
            sigma_rel=self._vol.sigma_rel,
            base_sigma=self._base_sigma,
            inventory_qty=self._inventory_qty,
            alpha_bps=alpha_bps,
            delta_ratio=delta_ratio,
            mo_imbalance=mo_imbalance,
            now_ns=ts_ns,
        )
        if decision.state != self._last_risk_state or decision.regime != self._last_regime:
            self.log.info(
                f"Risk decision regime={decision.regime} state={decision.state} "
                f"widen={decision.widen_factor:.2f} reduce={int(decision.reduce_levels)} "
                f"reason={decision.reason}",
            )
            self._last_risk_state = decision.state
            self._last_regime = decision.regime

        if decision.hedge_qty:
            self.log.info(f"Risk hedge triggered qty={decision.hedge_qty:.4f}")
            self._maybe_hedge(decision.hedge_qty)

        if decision.state == aurora_bindings.AuroraRiskState.PAUSE:
            self.log.info(f"Risk state PAUSE – cancelling all resting orders")
            self.cancel_all_orders(self.config.instrument_id)
            return

        grid_plan = self._grid_planner.plan(
            book=self._book,
            mid=mid,
            microprice=micro,
            sigma_px=sigma_px,
            alpha_bps=alpha_bps,
            tau_alpha_s=self._tau_alpha_s,
            tau_fill_s=self._tau_fill_s,
            inventory_qty=self._inventory_qty,
            widen_factor=decision.widen_factor,
            reduce_levels=int(decision.reduce_levels),
            bid_stats=self._queue_stats[OrderSide.BUY],
            ask_stats=self._queue_stats[OrderSide.SELL],
        )
        levels = list(grid_plan.orders())
        levels = self._apply_regime_filters(
            levels=levels,
            delta_eff=grid_plan.delta_eff,
            decision=decision,
        )
        center = grid_plan.center
        delta_eff = grid_plan.delta_eff
        target_inventory = grid_plan.target_inventory

        if levels:
            min_dist = min(level.distance for level in levels)
            max_dist = max(level.distance for level in levels)
            self.log.info(
                f"EV filter kept {len(levels)} levels dist=[{min_dist:.8f},{max_dist:.8f}] "
                f"delta={delta_eff:.8f} center-mid={center - mid:.8f}",
            )
        else:
            self.log.info(
                f"EV filter kept 0 levels (delta={delta_eff:.8f}, center={center:.8f}, center-mid={center - mid:.8f})",
            )

        regime_label = str(decision.regime)
        if not levels:
            if self._current_center is not None:
                self.log.debug(f"No positive EV orders – clearing book (center={center:.8f})")
                self.cancel_all_orders(self.config.instrument_id)
            self._current_center = center
            self._last_refresh_ns = ts_ns
            return

        pos_decision = self._pos_risk.on_inventory(
            inventory_qty=self._inventory_qty,
            target_inventory=target_inventory,
            regime=regime_label,
            ts_ns=ts_ns,
        )
        if pos_decision.trigger:
            self._maybe_taker_flatten(mid, target_inventory, ts_ns)

        should_refresh = self._should_refresh(center, delta_eff, ts_ns)
        if should_refresh:
            self._deploy_levels(levels)
            self._current_center = center
            self._last_refresh_ns = ts_ns
            self.log.info(
                f"Re-anchored grid center={center:.8f} levels={len(levels)} "
                f"delta={delta_eff:.8f} center-mid={center - mid:.8f} alpha={alpha_bps:.4f} "
                f"target_inv={target_inventory:.4f}",
            )

    def _should_refresh(self, center: float, delta: float, ts_ns: int) -> bool:
        if self._current_center is None:
            return True
        if abs(center - self._current_center) > self.config.grid.reanchor_rho * delta:
            return True
        elapsed_ms = (ts_ns - self._last_refresh_ns) / 1e6
        ttl_ms = max(self._order_ttl_ms, 1.0)
        timeout_ms = min(self.config.grid.reanchor_timeout_ms, ttl_ms)
        return elapsed_ms > timeout_ms

    def _base_delta(self, sigma_px: float, mid: float) -> float:
        fee_buffer_px = mid * self.config.grid.fee_buffer_bps / 10_000.0
        raw = (
            self.config.grid.k_sigma * sigma_px * math.sqrt(max(self._tau_fill_s, 0.0))
            + self.config.grid.k_s * self._tick_size
            + self.config.grid.k_f * fee_buffer_px
        )
        if self._tick_size <= 0:
            return raw
        steps = max(int(round(raw / self._tick_size)), 1)
        return steps * self._tick_size

    def _delta_ratio(self, base_delta: float) -> float:
        if base_delta <= 0:
            return 0.0
        x1 = 0.5 * base_delta
        entry_penalty = self.config.grid.delta_entry_ticks * self._tick_size
        return entry_penalty / max(x1, 1e-9)

    def _mo_imbalance(self) -> float:
        bid_lam = float(self._queue_stats[OrderSide.BUY].lambda_mo)
        ask_lam = float(self._queue_stats[OrderSide.SELL].lambda_mo)
        return bid_lam / max(ask_lam, 1e-9)

    def _apply_regime_filters(self, levels, delta_eff: float, decision) -> list:
        bias = getattr(decision, "trend_bias", None)
        if not levels or delta_eff <= 0 or bias is None:
            return levels
        clip = int(getattr(bias, "opposite_clip_levels", 0))
        if clip <= 0:
            return levels
        with_trend_is_bid = bool(getattr(bias, "with_trend_is_bid", True))
        keep_side = OrderSide.BUY if with_trend_is_bid else OrderSide.SELL
        filtered = []
        for level in levels:
            idx = max(int(level.distance / max(delta_eff, 1e-9) - 0.5), 0)
            if level.side == keep_side or idx >= clip:
                filtered.append(level)
        if len(filtered) != len(levels):
            self.log.info(
                f"Regime {decision.regime} clipped {len(levels) - len(filtered)} opposite-side levels",
                LogColor.YELLOW,
            )
        return filtered

    def _update_queue_from_snapshot(self, snapshot: dict, ts_ns: int, bid_qty: float, ask_qty: float) -> None:
        if self._last_snapshot is None:
            self._last_snapshot = snapshot
            self._last_snapshot_ts = ts_ns
            return
        dt = max((ts_ns - self._last_snapshot_ts) / 1e9, 1e-3)
        decay = self._queue_decay(dt)
        last_bid_qty = float(self._last_snapshot.get("bid_qty", 0.0))
        last_ask_qty = float(self._last_snapshot.get("ask_qty", 0.0))
        bid_drop = max(last_bid_qty - bid_qty, 0.0)
        ask_drop = max(last_ask_qty - ask_qty, 0.0)
        bid_stats = self._queue_stats[OrderSide.BUY]
        ask_stats = self._queue_stats[OrderSide.SELL]
        if bid_drop > 0:
            lam = bid_drop / dt
            bid_stats.update(lam, lam * 0.4, bid_drop, max(bid_drop**2, 1.0), decay)
        if ask_drop > 0:
            lam = ask_drop / dt
            ask_stats.update(lam, lam * 0.4, ask_drop, max(ask_drop**2, 1.0), decay)

        last_bid = float(self._last_snapshot.get("bid", 0.0))
        last_ask = float(self._last_snapshot.get("ask", 0.0))
        hit_bid = float(snapshot.get("bid", 0.0)) < last_bid - 1e-9
        hit_ask = float(snapshot.get("ask", 0.0)) > last_ask + 1e-9
        bid_stats.update_touch(hit_bid, dt, decay)
        ask_stats.update_touch(hit_ask, dt, decay)
        self._last_snapshot = snapshot
        self._last_snapshot_ts = ts_ns

    def _deploy_levels(self, levels) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        count = 0
        for level in levels:
            order = self._make_limit(level.side, level.price, level.quantity)
            if order is None:
                continue
            self.submit_order(order)
            count += 1
        self.log.info(f"Submitted {count} resting orders")

    def _meets_min_notional(self, price: float, qty: float) -> bool:
        """Return True if price*qty meets venue min notional; otherwise False."""
        if not self.instrument:
            return False
        notional = price * qty
        min_notional = None
        if self.instrument.min_notional:
            self.log.info("Using instrument min notional requirement", LogColor.YELLOW)
            min_notional = self.instrument.min_notional.as_double()
        elif self.instrument.quote_currency.code in {"USDT", "BUSD", "FDUSD", "USDC"}:
            # Binance USD-M futures commonly enforce 5 quote-min notional.
            min_notional = 5.0
        if min_notional is not None and notional < min_notional:
            self.log.info(
                f"Skip order notional below min: notional={notional:.6f} "
                f"min_required={min_notional:.6f}",
            )
            return False
        return True

    def _make_limit(self, side: OrderSide, price: float, qty: float) -> LimitOrder | None:
        if not self.instrument:
            return None
        min_qty = self.instrument.size_increment.as_double()
        if qty < min_qty:
            self.log.debug(f"Skip order qty below min: qty={qty:.6f} min_qty={min_qty:.6f}")
            return None
        if not self._meets_min_notional(price, qty):
            return None
        return self.order_factory.limit(
            instrument_id=self.config.instrument_id,
            order_side=side,
            price=self.instrument.make_price(Decimal(str(price))),
            quantity=self.instrument.make_qty(Decimal(str(qty))),
            time_in_force=TimeInForce.GTC,
            post_only=True,
        )

    def _maybe_hedge(self, qty: float) -> None:
        if qty == 0 or not self.instrument:
            return
        min_qty = self.instrument.size_increment.as_double()
        abs_qty = abs(qty)
        clip_steps = math.floor(abs_qty / min_qty) if min_qty > 0 else 0
        send_qty = clip_steps * min_qty
        if send_qty < min_qty:
            self.log.debug(
                f"Skip hedge qty below min size: raw_qty={abs_qty:.6f} min_qty={min_qty:.6f}",
            )
            return
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL if qty > 0 else OrderSide.BUY,
            quantity=self.instrument.make_qty(Decimal(str(send_qty))),
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)
        self.log.info(
            f"Hedge order submitted side={order.side.name} qty={order.quantity.as_double():.6f}",
        )

    def _build_grid_planner(self):
        """Build planner using q_min bumped to instrument min size."""
        cfg = self.config
        inv = cfg.inventory
        min_qty = self.instrument.size_increment.as_double() if self.instrument else inv.q_min
        eff_q_min = max(inv.q_min, min_qty)
        return aurora_bindings.AuroraGridPlanner(
            grid_levels=cfg.grid.levels,
            k_sigma=cfg.grid.k_sigma,
            k_s=cfg.grid.k_s,
            k_f=cfg.grid.k_f,
            fee_buffer_bps=cfg.grid.fee_buffer_bps,
            delta_entry_ticks=cfg.grid.delta_entry_ticks,
            exit_cost_bps=cfg.grid.exit_cost_bps,
            q_mm=cfg.grid.q_mm,
            unfilled_penalty_ticks=cfg.grid.unfilled_penalty_ticks,
            i_max=inv.i_max,
            i_soft=inv.i_soft,
            gamma=inv.gamma,
            kappa_alpha=inv.kappa_alpha,
            beta_i=inv.beta_i,
            theta_i=inv.theta_i,
            base_qty=inv.base_qty,
            eta=inv.eta,
            q_min=eff_q_min,
            q_max=inv.q_max,
            msg_rate_budget=cfg.exec.msg_rate_budget,
            tick_size=self._tick_size,
            min_p_fill=cfg.fill_model.min_p_fill,
            use_empirical_touch=cfg.fill_model.use_empirical_touch,
        )

    def _maybe_taker_flatten(self, mid: float, target_qty: float, ts_ns: int) -> None:
        if not self.instrument:
            return
        qty_gap = self._inventory_qty - target_qty
        if abs(qty_gap) < self.config.taker.taker_clip_qty:
            return
        if not self._pos_risk.allow_taker(ts_ns):
            return
        min_qty = self.instrument.size_increment.as_double()
        raw_clip = min(abs(qty_gap), self.config.taker.taker_clip_qty)
        # Floor to the nearest valid size increment to avoid zero-quantity errors.
        clip_steps = math.floor(raw_clip / min_qty) if min_qty > 0 else 0
        clip = clip_steps * min_qty
        if clip < min_qty:
            self.log.debug(
                f"Skip taker clip below min size: raw_clip={raw_clip:.6f} min_qty={min_qty:.6f}",
            )
            return
        side = OrderSide.SELL if qty_gap > 0 else OrderSide.BUY
        limit_px = calc_mo_slippage_price(mid, side.name, self.config.taker.taker_max_slippage_bps)
        if not self._meets_min_notional(limit_px, clip):
            return
        order: LimitOrder = self.order_factory.limit(
            instrument_id=self.config.instrument_id,
            order_side=side,
            price=self.instrument.make_price(Decimal(str(limit_px))),
            quantity=self.instrument.make_qty(Decimal(str(clip))),
            time_in_force=TimeInForce.IOC,
            post_only=False,
        )
        self.submit_order(order)
        self.log.info(
            f"Taker safety valve side={order.side.name} qty={clip:.6f} "
            f"target={target_qty:.6f} limit_px={limit_px:.6f}",
        )

    def _queue_decay(self, dt_s: float) -> float:
        window = max(self._queue_window_s, 1e-3)
        decay = math.exp(-max(dt_s, 1e-6) / window)
        return max(0.0, min(0.999999, decay))
