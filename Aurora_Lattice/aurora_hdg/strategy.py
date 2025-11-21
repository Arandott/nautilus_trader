"""Aurora HF Dynamic Grid strategy implementation."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque, Tuple

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
from .inventory import base_delta, build_grid_planner
from .position_risk import PositionRiskMonitor, calc_mo_slippage_price
from .regime import Regime, RegimeMachine
from .risk import RiskDecision, RiskState, RiskStateMachine


@dataclass(slots=True)
class AlphaSample:
    ts_ns: int
    mid: float
    features: Tuple[float, ...]


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
        self._alpha_model = aurora_bindings.RlsAlpha(
            dimension=4,
            params=aurora_bindings.RlsParams(
                forgetting=config.alpha.rls_forgetting,
                ridge=1.0,
                a_max_bps=config.alpha.a_max_bps,
            ),
        )
        self._alpha_lag_ns: int = int(config.alpha.tau_ms * 1e6)
        self._alpha_samples: Deque[AlphaSample] = deque()
        self._queue_stats = {
            OrderSide.BUY: QueueStats(lambda_mo=2.0, lambda_cancel=1.0, mean_mo=1.0, var_mo=1.0),
            OrderSide.SELL: QueueStats(lambda_mo=2.0, lambda_cancel=1.0, mean_mo=1.0, var_mo=1.0),
        }
        self._queue_window_s = max(config.fill_model.lambda_window_ms, 1) / 1000.0
        self._risk = RiskStateMachine(config.risk, config.inventory)
        self._regime = RegimeMachine(config.regime)
        self._pos_risk = PositionRiskMonitor(config.position_risk, config.taker, config.inventory.i_max)
        self._grid_planner = build_grid_planner(config)
        self._inventory_qty: float = 0.0
        self._last_snapshot: dict | None = None  # stores scalar L1 values
        self._last_snapshot_ts: int = 0
        self._base_sigma: float = 1e-6
        self._tau_alpha_s: float = self.config.alpha.tau_ms / 1000.0
        self._tau_fill_s: float = self.config.fill_model.tau_ms / 1000.0
        self._order_ttl_ms: float = self.config.fill_model.ttl_ratio * self.config.fill_model.tau_ms
        self._last_refresh_ns: int = 0
        self._current_center: float | None = None
        self._last_trade_ts: int | None = None
        self._last_risk_state: RiskState | None = None
        self._last_regime: Regime | None = None

    # --- lifecycle ---

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.config.instrument_id} missing")
            self.stop()
            return

        self._book.reset()
        self._book_factors.reset()
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
        self._process_snapshot(snapshot_values, deltas.ts_event)

    def on_trade_tick(self, tick: TradeTick) -> None:
        if tick.instrument_id != self.config.instrument_id:
            return
        qty = tick.size.as_double()
        dt = 1e-3
        if self._last_trade_ts:
            dt = max((tick.ts_event - self._last_trade_ts) / 1e9, 1e-3)
        self._last_trade_ts = tick.ts_event
        lam = qty / dt
        side = OrderSide.SELL if tick.aggressor_side == AggressorSide.BUY else OrderSide.BUY
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

    def _process_snapshot(self, snapshot: dict, ts_ns: int) -> None:
        mid = snapshot["mid"]
        micro = snapshot["microprice"]
        bid_qty = snapshot["bid_qty"]
        ask_qty = snapshot["ask_qty"]
        imbalance = snapshot["imbalance"]

        self._vol.update(mid)
        sigma_px = max(self._vol.sigma_px(mid), self.config.tick_size)
        self._base_sigma = 0.995 * self._base_sigma + 0.005 * self._vol.sigma_rel
        features = self._build_features(mid, micro, imbalance)
        alpha_bps = self._alpha_model.predict(features)
        self._alpha_samples.append(AlphaSample(ts_ns, mid, features))
        self._drain_alpha_queue(ts_ns, mid)
        self._update_queue_from_snapshot(snapshot, ts_ns, bid_qty, ask_qty)

        fee_buffer_px = mid * self.config.grid.fee_buffer_bps / 10_000.0
        delta_guess = base_delta(
            sigma_px=sigma_px,
            tick_size=self.config.tick_size,
            params=self.config.grid,
            fee_buffer_price=fee_buffer_px,
            tau_fill_s=self._tau_fill_s,
        )
        mo_imbalance = (self._queue_stats[OrderSide.BUY].lambda_mo + 1e-9) / (
            self._queue_stats[OrderSide.SELL].lambda_mo + 1e-9
        )
        delta_ratio = abs(micro - mid) / max(delta_guess, 1e-9)
        regime_decision = self._regime.update(
            alpha_bps=alpha_bps,
            delta_ratio=delta_ratio,
            mo_imbalance=mo_imbalance,
            sigma_rel=self._vol.sigma_rel,
            base_sigma=self._base_sigma,
            ts_ns=ts_ns,
        )
        if regime_decision.regime != self._last_regime:
            self.log.info(f"Regime transition {self._last_regime} -> {regime_decision.regime}")
            self._last_regime = regime_decision.regime

        decision = self._risk.on_metrics(
            sigma_rel=self._vol.sigma_rel,
            base_sigma=self._base_sigma,
            inventory_qty=self._inventory_qty,
            now_ns=ts_ns,
        )
        if decision.state != self._last_risk_state:
            self.log.info(f"Risk state transition {self._last_risk_state} -> {decision.state}")
            self._last_risk_state = decision.state

        if decision.hedge_qty:
            self.log.info(f"Risk hedge triggered qty={decision.hedge_qty:.4f}")
            self._maybe_hedge(decision.hedge_qty)

        if decision.state == RiskState.PAUSE:
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
            widen_factor=decision.widen_factor * regime_decision.delta_multiplier,
            reduce_levels=decision.reduce_levels + regime_decision.level_reduction,
            bid_stats=self._queue_stats[OrderSide.BUY],
            ask_stats=self._queue_stats[OrderSide.SELL],
        )
        levels = grid_plan.orders()
        center = grid_plan.center()
        delta_eff = grid_plan.delta_eff()
        target_inventory = grid_plan.target_inventory()

        levels = self._filter_by_regime(levels, delta_eff, regime_decision.regime)

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
            regime=regime_decision.regime.name,
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
                f"delta={delta_eff:.8f} alpha={alpha_bps:.4f} "
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

    def _build_features(self, mid: float, microprice: float, imbalance: float) -> Tuple[float, ...]:
        micro_skew = (microprice - mid) / max(self.config.tick_size, 1e-9)
        sigma_rel = self._vol.sigma_rel
        inv_ratio = self._inventory_qty / max(self.config.inventory.i_max, 1e-9)
        return (imbalance, micro_skew, sigma_rel, inv_ratio)

    def _drain_alpha_queue(self, ts_ns: int, current_mid: float) -> None:
        while self._alpha_samples and ts_ns - self._alpha_samples[0].ts_ns >= self._alpha_lag_ns:
            sample = self._alpha_samples.popleft()
            if sample.mid <= 0:
                continue
            ret_bps = ((current_mid - sample.mid) / sample.mid) * 1e4
            self._alpha_model.update(sample.features, ret_bps)
        if self._alpha_samples:
            self.log.debug(f"Alpha queue length={len(self._alpha_samples)}")

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

    def _make_limit(self, side: OrderSide, price: float, qty: float) -> LimitOrder | None:
        if not self.instrument:
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
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL if qty > 0 else OrderSide.BUY,
            quantity=self.instrument.make_qty(Decimal(str(abs(qty)))),
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)
        self.log.info(
            f"Hedge order submitted side={order.side.name} qty={order.quantity.as_double():.6f}",
        )

    def _filter_by_regime(self, levels, delta: float, regime: Regime):
        if regime == Regime.NORMAL:
            return levels
        filtered = []
        for level in levels:
            if regime == Regime.CHAOS:
                # Kill resting risk during chaos.
                continue
            if regime == Regime.TREND_UP:
                # Keep sells near/mid, keep deep buys as take-profit only.
                if level.side == OrderSide.SELL or level.distance >= 2 * delta:
                    filtered.append(level)
            elif regime == Regime.TREND_DOWN:
                if level.side == OrderSide.BUY or level.distance >= 2 * delta:
                    filtered.append(level)
        return filtered

    def _maybe_taker_flatten(self, mid: float, target_qty: float, ts_ns: int) -> None:
        if not self.instrument:
            return
        qty_gap = self._inventory_qty - target_qty
        if abs(qty_gap) < self.config.taker.taker_clip_qty:
            return
        if not self._pos_risk.allow_taker(ts_ns):
            return
        clip = min(abs(qty_gap), self.config.taker.taker_clip_qty)
        side = OrderSide.SELL if qty_gap > 0 else OrderSide.BUY
        limit_px = calc_mo_slippage_price(mid, side.name, self.config.taker.taker_max_slippage_bps)
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
