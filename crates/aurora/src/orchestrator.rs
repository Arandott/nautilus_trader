// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! Unified Aurora orchestrator (prototype): single order book + queue stats feeding alpha/risk/grid,
//! outputting ExecutionActions via ExecPolicy diff.

use std::f64::consts::E;

use anyhow::{Result, anyhow};
use nautilus_model::{
    data::{OrderBookDeltas, TradeTick},
    enums::BookType,
    identifiers::InstrumentId,
    orderbook::OrderBook,
};

use crate::{ActiveOrder, AlphaEngine, ExecPolicy, ExecutionActions, GridPlanner, OrderKind, PlannedOrder, QueueStats, RiskAdvisor};
use crate::fill::FillModel;
use crate::grid::{GridPlannerConfig, InventoryParams as GridInventoryParams};
use crate::risk::RegimeParams;

const MIN_TICK: f64 = 1e-9;

/// Runtime configuration snapshot for the orchestrator.
#[derive(Debug, Clone)]
pub struct OrchestratorConfig {
    pub instrument_id: InstrumentId,
    pub book_type: BookType,
    pub queue_window_ms: f64,
    pub tick_size: f64,
    pub base_sigma: f64,
    pub tau_alpha_s: f64,
    pub tau_fill_s: f64,
}

impl Default for OrchestratorConfig {
    fn default() -> Self {
        Self {
            instrument_id: InstrumentId::from("UNSET.UNSET"),
            book_type: BookType::L2_MBP,
            queue_window_ms: 300.0,
            tick_size: 0.0,
            base_sigma: 1e-6,
            tau_alpha_s: 0.3,
            tau_fill_s: 0.3,
        }
    }
}

#[derive(Debug, Clone)]
struct QueueState {
    bid_stats: QueueStats,
    ask_stats: QueueStats,
    last_bid_qty: f64,
    last_ask_qty: f64,
    last_bid_price: f64,
    last_ask_price: f64,
    last_ts: i64,
    window_s: f64,
    price_eps: f64,
}

impl QueueState {
    fn new(window_ms: f64, tick_size: f64) -> Self {
        Self {
            bid_stats: QueueStats::new(2.0, 1.0, 1.0, 1.0, 0.0),
            ask_stats: QueueStats::new(2.0, 1.0, 1.0, 1.0, 0.0),
            last_bid_qty: 0.0,
            last_ask_qty: 0.0,
            last_bid_price: 0.0,
            last_ask_price: 0.0,
            last_ts: 0,
            window_s: (window_ms.max(1.0)) / 1000.0,
            price_eps: tick_size.max(MIN_TICK),
        }
    }

    fn update_on_book(&mut self, book: &OrderBook, ts_ns: i64) {
        let bid_price = book.best_bid_price().map(|p| p.as_f64()).unwrap_or(0.0);
        let ask_price = book.best_ask_price().map(|p| p.as_f64()).unwrap_or(0.0);
        let bid_qty = book.best_bid_size().map(|q| q.as_f64()).unwrap_or(0.0);
        let ask_qty = book.best_ask_size().map(|q| q.as_f64()).unwrap_or(0.0);

        if self.last_ts == 0 {
            self.last_ts = ts_ns;
            self.last_bid_qty = bid_qty;
            self.last_ask_qty = ask_qty;
            self.last_bid_price = bid_price;
            self.last_ask_price = ask_price;
            return;
        }

        let dt = ((ts_ns - self.last_ts) as f64).max(1_000_000.0) / 1e9;
        let decay = decay_factor(dt, self.window_s);

        let bid_drop = (self.last_bid_qty - bid_qty).max(0.0);
        if bid_drop > 0.0 {
            let lam = bid_drop / dt;
            self.bid_stats
                .update(lam, lam * 0.4, bid_drop, bid_drop * bid_drop, decay);
        }
        let ask_drop = (self.last_ask_qty - ask_qty).max(0.0);
        if ask_drop > 0.0 {
            let lam = ask_drop / dt;
            self.ask_stats
                .update(lam, lam * 0.4, ask_drop, ask_drop * ask_drop, decay);
        }

        let hit_bid = bid_price < self.last_bid_price - self.price_eps;
        let hit_ask = ask_price > self.last_ask_price + self.price_eps;
        self.bid_stats.update_touch(hit_bid, dt, decay);
        self.ask_stats.update_touch(hit_ask, dt, decay);

        self.last_ts = ts_ns;
        self.last_bid_qty = bid_qty;
        self.last_ask_qty = ask_qty;
        self.last_bid_price = bid_price;
        self.last_ask_price = ask_price;
    }

    fn update_on_trade(&mut self, trade: &TradeTick, ts_ns: i64) {
        let qty = trade.size.as_f64();
        let dt = if self.last_ts == 0 {
            1e-3
        } else {
            ((ts_ns - self.last_ts) as f64).max(1_000_000.0) / 1e9
        };
        let decay = decay_factor(dt, self.window_s);
        let lam = qty / dt;
        match trade.aggressor_side {
            nautilus_model::enums::AggressorSide::Buyer => {
                self.ask_stats
                    .update(lam, lam * 0.3, qty, (qty * qty).max(1.0), decay)
            }
            nautilus_model::enums::AggressorSide::Seller => {
                self.bid_stats
                    .update(lam, lam * 0.3, qty, (qty * qty).max(1.0), decay)
            }
            _ => {}
        }
        self.last_ts = ts_ns;
    }

    fn mo_imbalance(&self) -> f64 {
        let bid = self.bid_stats.lambda_mo();
        let ask = self.ask_stats.lambda_mo();
        bid / ask.max(1e-9)
    }
}

fn decay_factor(dt_s: f64, window_s: f64) -> f64 {
    let w = window_s.max(1e-6);
    let exponent = -(dt_s.max(1e-6) / w);
    E.powf(exponent).clamp(0.0, 0.999_999)
}

/// Minimal orchestrator wiring book->queue->alpha->risk->grid->exec.
#[derive(Debug)]
pub struct AuroraOrchestrator<M: crate::AlphaModel> {
    book: OrderBook,
    queue: QueueState,
    alpha: AlphaEngine<M>,
    risk: RiskAdvisor,
    planner: GridPlanner,
    exec_policy: ExecPolicy,
    base_sigma: f64,
    tau_alpha_s: f64,
    tau_fill_s: f64,
    inventory_qty: f64,
}

impl<M: crate::AlphaModel> AuroraOrchestrator<M> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        cfg: OrchestratorConfig,
        alpha: AlphaEngine<M>,
        risk: RiskAdvisor,
        planner: GridPlanner,
        exec_policy: ExecPolicy,
    ) -> Result<Self> {
        let book = OrderBook::new(cfg.instrument_id, cfg.book_type);
        Ok(Self {
            book,
            queue: QueueState::new(cfg.queue_window_ms, cfg.tick_size),
            alpha,
            risk,
            planner,
            exec_policy,
            base_sigma: cfg.base_sigma.max(0.0),
            tau_alpha_s: cfg.tau_alpha_s.max(0.0),
            tau_fill_s: cfg.tau_fill_s.max(0.0),
            inventory_qty: 0.0,
        })
    }

    pub fn set_inventory(&mut self, qty: f64) {
        self.inventory_qty = qty;
    }

    pub fn handle_position(&mut self, qty: f64) {
        self.inventory_qty = qty;
    }

    pub fn handle_trade(
        &mut self,
        ts_ns: i64,
        trade: &TradeTick,
    ) -> Result<ExecutionActions> {
        self.queue.update_on_trade(trade, ts_ns);
        // Optional: trigger alpha/risk on trade events (placeholder)
        Ok(ExecutionActions::empty())
    }

    pub fn handle_orderbook(
        &mut self,
        ts_ns: i64,
        deltas: &OrderBookDeltas,
        active_orders: &[ActiveOrder],
        inventory_qty: f64,
    ) -> Result<ExecutionActions> {
        self.inventory_qty = inventory_qty;
        self.book
            .apply_deltas(deltas)
            .map_err(|err| anyhow!("apply_deltas failed: {err}"))?;
        self.queue.update_on_book(&self.book, ts_ns);

        let mid = mid_price(&self.book);
        if mid <= 0.0 {
            return Ok(ExecutionActions::empty());
        }

        let sigma_rel = 0.0; // placeholder; base_sigma used for risk ratios
        let sigma_px = self.base_sigma * mid;
        let alpha_bps = self
            .alpha
            .handle_order_book(ts_ns, &self.book, self.inventory_qty)?;

        let delta_ratio = 0.0; // TODO: derive from grid params if needed
        let decision = self.risk.advise(
            sigma_rel,
            self.base_sigma,
            self.inventory_qty,
            alpha_bps,
            delta_ratio,
            self.queue.mo_imbalance(),
            ts_ns as u64,
        );

        let microprice = micro_price(&self.book).unwrap_or(mid);
        let plan = self.planner.plan(
            &self.book,
            mid,
            microprice,
            sigma_px,
            alpha_bps,
            self.tau_alpha_s,
            self.tau_fill_s,
            self.inventory_qty,
            decision.widen_factor,
            decision.reduce_levels as usize,
            &self.queue.bid_stats,
            &self.queue.ask_stats,
        );

        let mut planned: Vec<PlannedOrder> = plan
            .orders()
            .iter()
            .map(|lvl| PlannedOrder {
                side: lvl.side,
                price: lvl.price,
                qty: lvl.quantity,
                kind: OrderKind::Grid,
            })
            .collect();

        if decision.hedge_qty != 0.0 {
            let side = if decision.hedge_qty > 0.0 {
                nautilus_model::enums::OrderSide::Sell
            } else {
                nautilus_model::enums::OrderSide::Buy
            };
            planned.push(PlannedOrder {
                side,
                price: mid,
                qty: decision.hedge_qty.abs(),
                kind: OrderKind::Active,
            });
        }

        let actions = self.exec_policy.diff(active_orders, &planned, ts_ns, Some(plan.center()));
        Ok(actions)
    }
}

fn mid_price(book: &OrderBook) -> f64 {
    match (book.best_bid_price(), book.best_ask_price()) {
        (Some(bid), Some(ask)) => (bid.as_f64() + ask.as_f64()) * 0.5,
        _ => 0.0,
    }
}

fn micro_price(book: &OrderBook) -> Option<f64> {
    let bid = book.best_bid_price()?.as_f64();
    let ask = book.best_ask_price()?.as_f64();
    let bid_qty = book.best_bid_size()?.as_f64();
    let ask_qty = book.best_ask_size()?.as_f64();
    let total = bid_qty + ask_qty;
    if total <= 0.0 {
        return None;
    }
    Some((ask * bid_qty + bid * ask_qty) / total)
}

/// Helper to build default planner/risk/exec config for prototyping.
#[allow(clippy::too_many_arguments)]
pub fn make_default_components(
    tick_size: f64,
    min_notional: f64,
    size_increment: f64,
    grid_cfg: GridPlannerConfig,
    inv_params: GridInventoryParams,
) -> (GridPlanner, ExecPolicy, RiskAdvisor) {
    let planner = GridPlanner::new(grid_cfg, FillModel::new(0.0, tick_size, false), false);
    let exec_cfg = crate::ExecPolicyConfig {
        tick_size,
        size_increment,
        min_notional,
        ..Default::default()
    };
    let exec = ExecPolicy::new(exec_cfg);
    let risk = RiskAdvisor::new(2.5, inv_params.i_soft, 0.0, 0.0, RegimeParams::default(), crate::risk::RiskMode::Full);
    (planner, exec, risk)
}
