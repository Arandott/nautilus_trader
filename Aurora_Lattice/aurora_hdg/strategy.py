"""Aurora HF Dynamic Grid strategy implementation."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque, Iterable, List, Tuple

from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.message import Event
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import OrderBookDeltas, TradeTick
from nautilus_trader.model.enums import AggressorSide, BookType, OrderSide, PositionSide, TimeInForce
from nautilus_trader.model.events import PositionChanged, PositionClosed, PositionOpened
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import LimitOrder, MarketOrder
from nautilus_trader.trading.strategy import Strategy

from .alpha import RLSParams, RecursiveLeastSquaresAlpha
from .config import AuroraHDGConfig
from .features import L1Snapshot, MidPriceVolEstimator, snapshot_from_book
from .fill import HittingQueueFillModel, QueueStats
from .inventory import (
    base_delta,
    compute_center,
    compute_target_inventory,
    level_distances,
    level_quantity,
)
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
        self._book: OrderBook | None = None
        self._vol = MidPriceVolEstimator()
        self._alpha_model = RecursiveLeastSquaresAlpha(
            dimension=4,
            params=RLSParams(
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
        self._fill_model = self._build_fill_model(config)
        self._inventory_qty: float = 0.0
        self._last_snapshot: L1Snapshot | None = None
        self._last_snapshot_ts: int = 0
        self._base_sigma: float = 1e-6
        self._last_refresh_ns: int = 0
        self._current_center: float | None = None
        self._last_trade_ts: int | None = None
        self._last_risk_state: RiskState | None = None

    # --- lifecycle ---

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.config.instrument_id} missing")
            self.stop()
            return

        self._book = OrderBook(
            instrument_id=self.config.instrument_id,
            book_type=BookType.L2_MBP,
        )
        self.subscribe_order_book_deltas(self.config.instrument_id)
        self.subscribe_trade_ticks(self.config.instrument_id)
        self.log.info(
            f"Aurora HDG started for instrument {self.config.instrument_id}",
            LogColor.GREEN,
        )

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.log.info(f"Aurora HDG stopped", LogColor.YELLOW)

    # --- data handlers ---

    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        if not self._book:
            return
        self._book.apply_deltas(deltas)
        snapshot = snapshot_from_book(self._book)
        if snapshot is None:
            return
        self._process_snapshot(snapshot, deltas.ts_event)

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

    def _process_snapshot(self, snapshot: L1Snapshot, ts_ns: int) -> None:
        self._vol.update(snapshot.mid)
        sigma_px = max(self._vol.sigma_px(snapshot.mid), self.config.tick_size)
        self._base_sigma = 0.995 * self._base_sigma + 0.005 * self._vol.sigma_rel
        features = self._build_features(snapshot)
        alpha_bps = self._alpha_model.predict(features)
        self._alpha_samples.append(AlphaSample(ts_ns, snapshot.mid, features))
        self._drain_alpha_queue(ts_ns, snapshot.mid)
        self._update_queue_from_snapshot(snapshot, ts_ns)

        fee_buffer_px = snapshot.mid * self.config.grid.fee_buffer_bps / 1e4
        delta = base_delta(sigma_px, self.config.tick_size, self.config.grid, fee_buffer_px)
        tau_s = self.config.alpha.tau_ms / 1000.0

        target_inventory = compute_target_inventory(alpha_bps, sigma_px, tau_s, self.config.inventory)
        center = compute_center(
            snapshot.microprice,
            self._inventory_qty,
            target_inventory,
            delta,
            alpha_bps,
            self.config.inventory,
        )

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

        delta_eff = delta * decision.widen_factor
        fee_limit = max(1, self.config.exec.msg_rate_budget // 2)
        level_cap = min(self.config.grid.levels - decision.reduce_levels, fee_limit)
        if level_cap <= 0:
            level_cap = 1
        distances = level_distances(level_cap, delta_eff)
        orders = self._build_order_plan(
            center=center,
            distances=distances,
            sigma_px=sigma_px,
            tau_s=tau_s,
            alpha_bps=alpha_bps,
            fee_buffer_px=fee_buffer_px,
            decision=decision,
            target_inventory=target_inventory,
        )

        if not orders:
            if self._current_center is not None:
                self.log.debug(f"No positive EV orders – clearing book (center={center:.8f})")
                self.cancel_all_orders(self.config.instrument_id)
            self._current_center = center
            self._last_refresh_ns = ts_ns
            return

        should_refresh = self._should_refresh(center, delta_eff, ts_ns)
        if should_refresh:
            self._deploy_orders(orders)
            self._current_center = center
            self._last_refresh_ns = ts_ns
            self.log.info(
                f"Re-anchored grid center={center:.8f} levels={len(orders)} "
                f"delta={delta_eff:.8f} alpha={alpha_bps:.4f} "
                f"target_inv={target_inventory:.4f}",
            )

    def _should_refresh(self, center: float, delta: float, ts_ns: int) -> bool:
        if self._current_center is None:
            return True
        if abs(center - self._current_center) > self.config.grid.reanchor_rho * delta:
            return True
        elapsed_ms = (ts_ns - self._last_refresh_ns) / 1e6
        return elapsed_ms > self.config.grid.reanchor_timeout_ms

    def _build_features(self, snapshot: L1Snapshot) -> Tuple[float, ...]:
        imbalance = snapshot.imbalance
        micro_skew = (snapshot.microprice - snapshot.mid) / max(self.config.tick_size, 1e-9)
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

    def _update_queue_from_snapshot(self, snapshot: L1Snapshot, ts_ns: int) -> None:
        if self._last_snapshot is None:
            self._last_snapshot = snapshot
            self._last_snapshot_ts = ts_ns
            return
        dt = max((ts_ns - self._last_snapshot_ts) / 1e9, 1e-3)
        decay = self._queue_decay(dt)
        bid_drop = max(self._last_snapshot.bid_qty - snapshot.bid_qty, 0.0)
        ask_drop = max(self._last_snapshot.ask_qty - snapshot.ask_qty, 0.0)
        bid_stats = self._queue_stats[OrderSide.BUY]
        ask_stats = self._queue_stats[OrderSide.SELL]
        if bid_drop > 0:
            lam = bid_drop / dt
            bid_stats.update(lam, lam * 0.4, bid_drop, max(bid_drop**2, 1.0), decay)
        if ask_drop > 0:
            lam = ask_drop / dt
            ask_stats.update(lam, lam * 0.4, ask_drop, max(ask_drop**2, 1.0), decay)

        hit_bid = snapshot.bid < self._last_snapshot.bid - 1e-9
        hit_ask = snapshot.ask > self._last_snapshot.ask + 1e-9
        bid_stats.update_touch(hit_bid, dt, decay)
        ask_stats.update_touch(hit_ask, dt, decay)
        self._last_snapshot = snapshot
        self._last_snapshot_ts = ts_ns

    def _build_order_plan(
        self,
        center: float,
        distances: Iterable[float],
        sigma_px: float,
        tau_s: float,
        alpha_bps: float,
        fee_buffer_px: float,
        decision: RiskDecision,
        target_inventory: float,
    ) -> List[tuple[OrderSide, float, float]]:
        orders: List[tuple[OrderSide, float, float]] = []
        for idx, distance in enumerate(distances):
            for side in (OrderSide.BUY, OrderSide.SELL):
                price = center - distance if side == OrderSide.BUY else center + distance
                if price <= 0:
                    continue
                qty = level_quantity(
                    level_index=idx,
                    params=self.config.inventory,
                    current_inventory=self._inventory_qty,
                    target_inventory=target_inventory,
                    side=side,
                )
                ev = self._expected_value(
                    side=side,
                    distance=distance,
                    price=price,
                    sigma_px=sigma_px,
                    tau_s=tau_s,
                    fee_buffer_px=fee_buffer_px,
                    qty=qty,
                )
                if ev <= 0:
                    continue
                orders.append((side, price, qty))
                self.log.debug(
                    f"Order candidate side={side.name} level={idx} "
                    f"price={price:.8f} qty={qty:.6f} ev={ev:.8f}",
                )
        return orders[: self.config.exec.msg_rate_budget]

    def _expected_value(
        self,
        side: OrderSide,
        distance: float,
        price: float,
        sigma_px: float,
        tau_s: float,
        fee_buffer_px: float,
        qty: float,
    ) -> float:
        queue_ahead = self._queue_ahead(price, side)
        mu = 0.0  # drift is folded into alpha via center skew
        stats = self._queue_stats[side]
        p_fill = self._fill_model.p_fill(
            side=side,
            distance=distance,
            mu=mu,
            sigma_px=sigma_px,
            horizon_s=tau_s,
            queue_ahead=queue_ahead,
            stats=stats,
        )
        pickoff = 0.5 * sigma_px
        variance_penalty = (1 - p_fill) * self.config.inventory.gamma * abs(self._inventory_qty) * sigma_px * (tau_s**0.5)
        edge = distance - fee_buffer_px - pickoff
        return qty * (p_fill * edge - variance_penalty)

    def _queue_ahead(self, price: float, side: OrderSide) -> float:
        if not self._book:
            return 0.0
        levels = self._book.bids() if side == OrderSide.BUY else self._book.asks()
        total = 0.0
        for level in levels:
            lvl_price = level.price.as_double()
            if side == OrderSide.BUY and lvl_price >= price:
                total += sum(order.quantity.as_double() for order in level.orders())
            elif side == OrderSide.SELL and lvl_price <= price:
                total += sum(order.quantity.as_double() for order in level.orders())
            else:
                break
        return total

    def _deploy_orders(self, plan: List[tuple[OrderSide, float, float]]) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        for side, price, qty in plan:
            order = self._make_limit(side, price, qty)
            if order is None:
                continue
            self.submit_order(order)
        self.log.info(f"Submitted {len(plan)} resting orders")

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

    def _build_fill_model(self, config: AuroraHDGConfig) -> HittingQueueFillModel:
        impl = config.fill_model.impl.lower()
        if impl not in {"hittingqueue", "hitting_queue"}:
            raise ValueError(f"Unsupported fill model `{config.fill_model.impl}`")
        self.log.info(
            f"Using hitting queue fill model impl={config.fill_model.impl} "
            f"min_p={config.fill_model.min_p_fill:.4f} "
            f"empirical_touch={config.fill_model.use_empirical_touch}",
        )
        return HittingQueueFillModel(
            min_p=config.fill_model.min_p_fill,
            tick_size=config.tick_size,
            use_empirical_touch=config.fill_model.use_empirical_touch,
        )

    def _queue_decay(self, dt_s: float) -> float:
        window = max(self._queue_window_s, 1e-3)
        decay = math.exp(-max(dt_s, 1e-6) / window)
        return max(0.0, min(0.999999, decay))
