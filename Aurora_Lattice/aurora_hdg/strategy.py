"""Aurora HF Dynamic Grid strategy implementation (Rust orchestrator driven)."""

from __future__ import annotations
from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.message import Event
from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import BookType, OrderSide, PositionSide, TimeInForce
from nautilus_trader.model.events import PositionChanged, PositionClosed, PositionOpened
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy

from .config import AuroraHDGConfig


class AuroraHdgStrategy(Strategy):
    """HF Dynamic Grid strategy built on Nautilus (Rust orchestrator pipeline)."""

    def __init__(self, config: AuroraHDGConfig) -> None:
        super().__init__(config)
        self.instrument: Instrument | None = None
        self._book_type = BookType.L2_MBP
        self._pyo3_instrument_id = nautilus_pyo3.InstrumentId.from_str(self.config.instrument_id.value)
        self._pyo3_book_type = nautilus_pyo3.BookType(self._book_type.name)
        self._tick_size: float = float(config.tick_size)
        self._inventory_qty: float = 0.0
        self._order_ttl_ms: float = self.config.fill_model.ttl_ratio * self.config.fill_model.tau_ms
        self._orchestrator: aurora_bindings.AuroraOrchestrator | None = None

    # --- lifecycle ---

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.config.instrument_id} missing")
            self.stop()
            return

        self._tick_size = self.instrument.price_increment.as_double()
        self.log.info(f"Using instrument tick_size={self._tick_size:.8f}", LogColor.YELLOW)

        try:
            self._orchestrator = self._build_orchestrator()
            self._orchestrator.set_inventory(self._inventory_qty)
        except Exception as exc:  # noqa: BLE001
            self.log.error(f"Failed to build Aurora orchestrator: {exc}")
            self.stop()
            return

        self.subscribe_order_book_deltas(
            self.config.instrument_id,
            self._book_type,
            managed=False,
            pyo3_conversion=True,
        )
        self.subscribe_trade_ticks(self.config.instrument_id)
        self.log.info(f"Aurora HDG started for instrument {self.config.instrument_id}", LogColor.GREEN)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.log.info("Aurora HDG stopped", LogColor.YELLOW)

    # --- data handlers ---

    def on_order_book_deltas(self, deltas: nautilus_pyo3.OrderBookDeltas) -> None:
        orch = self._orchestrator  # assume已初始化
        if orch is None:  # pragma: no cover - 硬失败以暴露错误
            raise RuntimeError("orchestrator not initialized")
        try:
            actions = orch.handle_orderbook(
                deltas=deltas,
                active_orders=self._active_orders_view(),
                inventory_qty=self._inventory_qty,
                ts_ns=deltas.ts_event,
            )
        except Exception as exc:  # noqa: BLE001
            self.log.error(f"Orchestrator handle_orderbook failed: {exc}")
            return
        self._apply_actions(actions)

    def on_trade_tick(self, tick: TradeTick) -> None:
        orch = self._orchestrator
        if orch is None:  # pragma: no cover
            raise RuntimeError("orchestrator not initialized")
        try:
            actions = orch.handle_trade(trade=tick, ts_ns=tick.ts_event)
        except Exception as exc:  # noqa: BLE001
            self.log.debug(f"Orchestrator handle_trade failed: {exc}")
            return
        self._apply_actions(actions)

    def on_event(self, event: Event) -> None:
        if isinstance(event, (PositionOpened, PositionChanged)):
            qty = event.quantity.as_double()
            if event.side == PositionSide.SHORT:
                qty = -qty
            prev_qty = self._inventory_qty
            self._inventory_qty = qty
            if self._orchestrator:
                self._orchestrator.set_inventory(qty)
            self.log.info(
                f"Inventory updated via position event prev={prev_qty:.4f} now={self._inventory_qty:.4f}"
            )
        elif isinstance(event, PositionClosed):
            self._inventory_qty = 0.0
            if self._orchestrator:
                self._orchestrator.set_inventory(0.0)
            self.log.info("Inventory reset to flat after position close")

    # --- core helpers ---

    def _apply_actions(self, actions: aurora_bindings.ExecutionActions) -> None:
        cancel_targets = self._match_cancel_orders(actions.cancel)
        if cancel_targets:
            try:
                self.cancel_orders(cancel_targets)
            except Exception as exc:  # pragma: no cover - 防御
                self.log.error(f"Batch cancel failed, falling back to cancel_all: {exc}")
                self.cancel_all_orders(self.config.instrument_id)
        elif actions.cancel:
            # 有撤单意图但未匹配到，保险起见全撤
            self.cancel_all_orders(self.config.instrument_id)

        if actions.submit:
            self._submit_order_intents(actions.submit)

    def _match_cancel_orders(self, cancels: list[aurora_bindings.CancelReq]):
        if not cancels:
            return []
        try:
            open_orders = list(self.cache.orders_open(instrument_id=self.config.instrument_id))
        except Exception as exc:  # pragma: no cover - 防御
            self.log.error(f"Failed to fetch open orders for cancel matching: {exc}")
            return []

        by_id = {o.client_order_id.value: o for o in open_orders if getattr(o, \"client_order_id\", None)}
        remaining = []
        for o in open_orders:
            coid = getattr(o, \"client_order_id\", None)
            if coid is None or coid.value not in by_id:
                remaining.append(o)

        matched = []
        tick = max(self._tick_size, 1e-9)
        for req in cancels:
            order = None
            if req.client_order_id and req.client_order_id in by_id:
                order = by_id[req.client_order_id]
            else:
                # 退化匹配：按 side+price 近似匹配
                for o in remaining:
                    if o.side != req.side:
                        continue
                    price = float(o.price.as_double()) if getattr(o, \"price\", None) else 0.0
                    if abs(price - req.price) <= 0.5 * tick:
                        order = o
                        remaining.remove(o)
                        break
            if order is not None:
                matched.append(order)
        return matched

    def _submit_order_intents(self, intents: list[aurora_bindings.OrderIntent]) -> None:
        count = 0
        for intent in intents:
            tif = intent.tif or (TimeInForce.GTC if intent.post_only else TimeInForce.IOC)
            order = self._make_limit(intent.side, intent.price, intent.qty, intent.post_only, tif)
            if order is None:
                continue
            self.submit_order(order)
            count += 1
        if count:
            self.log.info(f"Submitted {count} orders via orchestrator actions")

    def _meets_min_notional(self, price: float, qty: float) -> bool:
        if not self.instrument:
            return False
        notional = price * qty
        min_notional = None
        if self.instrument.min_notional:
            min_notional = self.instrument.min_notional.as_double()
        elif self.instrument.quote_currency.code in {"USDT", "BUSD", "FDUSD", "USDC"}:
            min_notional = 5.0
        if min_notional is not None and notional < min_notional:
            self.log.debug(
                f"Skip order notional below min: notional={notional:.6f} min_required={min_notional:.6f}"
            )
            return False
        return True

    def _make_limit(
        self,
        side: OrderSide,
        price: float,
        qty: float,
        post_only: bool,
        tif: TimeInForce,
    ) -> LimitOrder | None:
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
            time_in_force=tif,
            post_only=post_only,
        )

    def _build_orchestrator(self) -> aurora_bindings.AuroraOrchestrator:
        cfg = self.config
        features = ["imbalance", "micro_skew", "sigma_rel"]
        rls_model = aurora_bindings.RlsAlpha(
            dimension=len(features),
            params=aurora_bindings.RlsParams(
                forgetting=cfg.alpha.rls_forgetting,
                ridge=1.0,
                a_max_bps=cfg.alpha.a_max_bps,
            ),
        )
        alpha_params = aurora_bindings.AlphaEngineParams(
            lag_ns=int(cfg.alpha.tau_ms * 1e6),
            tick_size=self._tick_size,
            i_max=cfg.inventory.i_max,
            time_stride_ns=0,
            count_stride=1,
            min_updates_for_output=0,
            label_queue_len=4096,
            base_sigma=1e-6,
            features=features,
        )
        regime_params = aurora_bindings.AuroraRegimeParams(
            alpha_gate_bps=cfg.regime.alpha_gate_bps,
            trend_delta_ratio_threshold=cfg.regime.trend_delta_ratio_threshold,
            mo_imbalance_threshold=cfg.regime.mo_imbalance_threshold,
            hysteresis_ms=cfg.regime.hysteresis_ms,
            trend_opposite_clip_levels=cfg.regime.trend_opposite_clip_levels,
            trend_widen_mult=cfg.regime.trend_widen_mult,
            trend_reduce_levels=cfg.regime.trend_reduce_levels,
            chaos_widen_mult=cfg.regime.chaos_widen_mult,
            chaos_reduce_levels=cfg.regime.chaos_reduce_levels,
            pause_on_chaos=cfg.regime.pause_on_chaos,
        )
        risk = aurora_bindings.AuroraRiskAdvisor(
            vol_shock_sigma_mult=cfg.risk.shock_mode_sigma_mult,
            inventory_soft_limit=cfg.inventory.i_soft,
            hedge_cooldown_ms=cfg.risk.hedge_cooldown_ms,
            hedge_min_qty=cfg.risk.hedge_min_qty,
            regime_params=regime_params,
            mode=cfg.risk.mode,
        )
        grid_planner = self._build_grid_planner()
        exec_policy = self._build_exec_policy()
        orch_cfg = aurora_bindings.OrchestratorConfig(
            instrument_id=self._pyo3_instrument_id,
            book_type=self._pyo3_book_type,
            queue_window_ms=cfg.fill_model.lambda_window_ms,
            tick_size=self._tick_size,
            base_sigma=1e-6,
            tau_alpha_s=cfg.alpha.tau_ms / 1000.0,
            tau_fill_s=cfg.fill_model.tau_ms / 1000.0,
        )
        return aurora_bindings.AuroraOrchestrator(
            config=orch_cfg,
            model=rls_model,
            grid_planner=grid_planner,
            risk_advisor=risk,
            exec_policy=exec_policy,
            alpha_params=alpha_params,
        )

    def _build_grid_planner(self) -> aurora_bindings.AuroraGridPlanner:
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
            use_fill_model=False,
        )

    def _build_exec_policy(self) -> aurora_bindings.ExecPolicy:
        min_notional = 0.0
        size_increment = 0.0
        if self.instrument:
            if self.instrument.min_notional:
                min_notional = self.instrument.min_notional.as_double()
            size_increment = self.instrument.size_increment.as_double()
        cfg = aurora_bindings.ExecPolicyConfig(
            tick_size=self._tick_size,
            size_increment=size_increment,
            min_notional=min_notional,
            ttl_ns=int(self._order_ttl_ms * 1e6),
            reanchor_eps_ticks=0,
            max_changes_per_cycle=10_000,
            price_eps_ticks=0,
            qty_eps=0.0,
        )
        return aurora_bindings.ExecPolicy(cfg)

    def _active_orders_view(self) -> list[aurora_bindings.ActiveOrder]:
        orders: list[aurora_bindings.ActiveOrder] = []
        try:
            open_orders = self.cache.orders_open(instrument_id=self.config.instrument_id)
        except Exception as exc:  # pragma: no cover - 防御
            self.log.debug(f"Failed to fetch open orders for ExecPolicy: {exc}")
            return orders
        for order in open_orders:
            try:
                ts = getattr(order, "ts_last_update", None) or getattr(order, "ts_event", 0)
                qty = float(getattr(order, "leaves_qty", order.quantity).as_double())
                price = float(order.price.as_double()) if getattr(order, "price", None) else 0.0
                kind = aurora_bindings.OrderKind.GRID
                if getattr(order, "post_only", True) is False:
                    kind = aurora_bindings.OrderKind.ACTIVE
                orders.append(
                    aurora_bindings.ActiveOrder(
                        client_order_id=order.client_order_id.value,
                        side=order.side,
                        price=price,
                        qty=qty,
                        ts_placed_ns=int(ts),
                        kind=kind,
                    )
                )
            except Exception as exc:  # pragma: no cover - 防御
                self.log.debug(f"Skip order in ExecPolicy view: {exc}")
        return orders
