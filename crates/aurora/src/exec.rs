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

//! Execution diffing policy: given current active orders and a new plan, produce submit/cancel
//! actions with basic validity checks (tick/size alignment, min notional, TTL/re-anchor).

use std::collections::HashMap;

use nautilus_model::enums::OrderSide;

const MIN_NOTIONAL_EPS: f64 = 1e-9;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum OrderKind {
    Grid,
    Active, // 主动型（合并 hedge/taker）
}

#[derive(Debug, Clone)]
pub struct OrderIntent {
    pub side: OrderSide,
    pub price: f64,
    pub qty: f64,
    pub post_only: bool,
    pub kind: OrderKind,
}

#[derive(Debug, Clone)]
pub struct CancelReq {
    pub client_order_id: Option<String>,
    pub side: OrderSide,
    pub price: f64,
}

#[derive(Debug, Clone)]
pub struct ExecutionActions {
    pub submit: Vec<OrderIntent>,
    pub cancel: Vec<CancelReq>,
}

impl ExecutionActions {
    pub fn empty() -> Self {
        Self {
            submit: Vec::new(),
            cancel: Vec::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ActiveOrder {
    pub client_order_id: Option<String>,
    pub side: OrderSide,
    pub price: f64,
    pub qty: f64,
    pub ts_placed_ns: i64,
    pub kind: OrderKind,
}

#[derive(Debug, Clone)]
pub struct PlannedOrder {
    pub side: OrderSide,
    pub price: f64,
    pub qty: f64,
    pub kind: OrderKind,
}

#[derive(Debug, Clone)]
pub struct ExecPolicyConfig {
    pub tick_size: f64,
    pub size_increment: f64,
    pub min_notional: f64,
    pub ttl_ns: i64,
    pub reanchor_eps_ticks: i64,
    pub max_changes_per_cycle: usize,
    pub price_eps_ticks: i64,
    pub qty_eps: f64,
}

impl Default for ExecPolicyConfig {
    fn default() -> Self {
        Self {
            tick_size: 0.0,
            size_increment: 0.0,
            min_notional: 0.0,
            ttl_ns: 0,
            reanchor_eps_ticks: 0,
            max_changes_per_cycle: usize::MAX,
            price_eps_ticks: 0,
            qty_eps: 0.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ExecPolicy {
    cfg: ExecPolicyConfig,
}

impl ExecPolicy {
    pub fn new(cfg: ExecPolicyConfig) -> Self {
        Self { cfg }
    }

    /// Compute submit/cancel actions given active orders and a planned book.
    pub fn diff(
        &self,
        active: &[ActiveOrder],
        planned: &[PlannedOrder],
        ts_now: i64,
        center: Option<f64>,
    ) -> ExecutionActions {
        let mut cancel = Vec::new();
        let mut matched_active: HashMap<usize, bool> = HashMap::new();
        let price_eps = (self.cfg.price_eps_ticks as f64) * self.cfg.tick_size.max(0.0);
        let reanchor_eps = (self.cfg.reanchor_eps_ticks as f64) * self.cfg.tick_size.max(0.0);

        // TTL / re-anchor checks on active orders
        for (idx, order) in active.iter().enumerate() {
            let mut should_cancel = false;
            if self.cfg.ttl_ns > 0 && order.ts_placed_ns > 0 {
                if ts_now.saturating_sub(order.ts_placed_ns) >= self.cfg.ttl_ns {
                    should_cancel = true;
                }
            }
            if let Some(center_px) = center {
                if center_px > 0.0 && reanchor_eps > 0.0 {
                    if (order.price - center_px).abs() > reanchor_eps {
                        should_cancel = true;
                    }
                }
            }
            if should_cancel {
                cancel.push(CancelReq {
                    client_order_id: order.client_order_id.clone(),
                    side: order.side,
                    price: order.price,
                });
                matched_active.insert(idx, true);
            }
        }

        let mut submit = Vec::new();
        let mut active_by_key: HashMap<(OrderSide, i64, OrderKind), Vec<(usize, &ActiveOrder)>> =
            HashMap::new();

        for (idx, order) in active.iter().enumerate() {
            let price_key = quantize(order.price, self.cfg.tick_size);
            active_by_key
                .entry((order.side, price_key, order.kind))
                .or_default()
                .push((idx, order));
        }

        for plan in planned.iter().filter_map(|p| self.sanitize_plan(p)) {
            let price_key = quantize(plan.price, self.cfg.tick_size);
            let qty_clamped = plan.qty;

            let mut matched = false;
            if let Some(candidates) = active_by_key.get(&(plan.side, price_key, plan.kind)) {
                for (idx, ao) in candidates {
                    if matched_active.get(idx).copied().unwrap_or(false) {
                        continue;
                    }
                    if (ao.price - plan.price).abs() <= price_eps
                        && (ao.qty - qty_clamped).abs() <= self.cfg.qty_eps
                    {
                        matched_active.insert(*idx, true);
                        matched = true;
                        break;
                    }
                }
            }

            if !matched {
                submit.push(OrderIntent {
                    side: plan.side,
                    price: plan.price,
                    qty: qty_clamped,
                    post_only: matches!(plan.kind, OrderKind::Grid),
                    kind: plan.kind,
                });
            }
        }

        // Cancel unmatched (non TTL/reanchor) active orders
        for (idx, order) in active.iter().enumerate() {
            if matched_active.get(&idx).copied().unwrap_or(false) {
                continue;
            }
            // Still present but not matched by plan -> cancel
            cancel.push(CancelReq {
                client_order_id: order.client_order_id.clone(),
                side: order.side,
                price: order.price,
            });
        }

        // Apply max_changes_per_cycle (cancel 优先)
        let mut actions = ExecutionActions { submit, cancel };
        self.truncate(&mut actions);
        actions
    }

    fn sanitize_plan(&self, plan: &PlannedOrder) -> Option<PlannedOrder> {
        let tick = self.cfg.tick_size.max(0.0);
        let size_inc = self.cfg.size_increment.max(0.0);
        if plan.price <= 0.0 || plan.qty <= 0.0 {
            return None;
        }
        let price = if tick > 0.0 {
            (plan.price / tick).round() * tick
        } else {
            plan.price
        };
        let qty = if size_inc > 0.0 {
            (plan.qty / size_inc).floor() * size_inc
        } else {
            plan.qty
        };
        if qty <= 0.0 {
            return None;
        }
        let notional = price * qty;
        if notional + MIN_NOTIONAL_EPS < self.cfg.min_notional.max(0.0) {
            return None;
        }
        qty
            .is_finite()
            .then_some(PlannedOrder {
                side: plan.side,
                price,
                qty,
                kind: plan.kind,
            })
    }

    fn truncate(&self, actions: &mut ExecutionActions) {
        let max_changes = self.cfg.max_changes_per_cycle;
        if actions.cancel.len() + actions.submit.len() <= max_changes {
            return;
        }
        // Cancel 优先，其次截断 submit
        if actions.cancel.len() > max_changes {
            actions.cancel.truncate(max_changes);
            actions.submit.clear();
        } else {
            let remain = max_changes.saturating_sub(actions.cancel.len());
            actions.submit.truncate(remain);
        }
    }
}

fn quantize(price: f64, tick: f64) -> i64 {
    if tick <= 0.0 {
        return (price * 1e6).round() as i64;
    }
    (price / tick).round() as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    fn planned(side: OrderSide, price: f64, qty: f64) -> PlannedOrder {
        PlannedOrder {
            side,
            price,
            qty,
            kind: OrderKind::Grid,
        }
    }

    fn active(side: OrderSide, price: f64, qty: f64) -> ActiveOrder {
        ActiveOrder {
            client_order_id: Some("ID".to_string()),
            side,
            price,
            qty,
            ts_placed_ns: 0,
            kind: OrderKind::Grid,
        }
    }

    #[test]
    fn force_rehang_cancels_all() {
        // No force-rehang path anymore; ensure diff returns sane actions
        let policy = ExecPolicy::new(ExecPolicyConfig::default());
        let active = vec![active(OrderSide::Buy, 100.0, 1.0)];
        let planned = vec![planned(OrderSide::Buy, 101.0, 1.0)];
        let actions = policy.diff(&active, &planned, 0, None);
        assert_eq!(actions.cancel.len(), 1);
        assert_eq!(actions.submit.len(), 1);
    }

    #[test]
    fn matched_orders_not_resubmitted_when_not_forced() {
        let cfg = ExecPolicyConfig {
            price_eps_ticks: 1,
            tick_size: 0.1,
            ..ExecPolicyConfig::default()
        };
        let policy = ExecPolicy::new(cfg);
        let active = vec![active(OrderSide::Buy, 100.0, 1.0)];
        let planned = vec![planned(OrderSide::Buy, 100.05, 1.0)];
        let actions = policy.diff(&active, &planned, 0, None);
        assert!(actions.submit.is_empty());
        assert!(actions.cancel.is_empty());
    }

    #[test]
    fn ttl_triggers_cancel() {
        let cfg = ExecPolicyConfig {
            ttl_ns: 10,
            ..ExecPolicyConfig::default()
        };
        let policy = ExecPolicy::new(cfg);
        let mut act = active(OrderSide::Buy, 100.0, 1.0);
        act.ts_placed_ns = 0;
        let actions = policy.diff(&[act], &[], 20, None);
        assert_eq!(actions.cancel.len(), 1);
    }

    #[test]
    fn min_notional_filters_plan() {
        let cfg = ExecPolicyConfig {
            min_notional: 10.0,
            ..ExecPolicyConfig::default()
        };
        let policy = ExecPolicy::new(cfg);
        let planned = vec![planned(OrderSide::Buy, 1.0, 5.0)];
        let actions = policy.diff(&[], &planned, 0, None);
        assert!(actions.submit.is_empty());
    }

    #[test]
    fn max_changes_truncates() {
        let cfg = ExecPolicyConfig {
            max_changes_per_cycle: 1,
            ..ExecPolicyConfig::default()
        };
        let policy = ExecPolicy::new(cfg);
        let active = vec![active(OrderSide::Buy, 100.0, 1.0)];
        let planned = vec![planned(OrderSide::Sell, 101.0, 1.0)];
        let actions = policy.diff(&active, &planned, 0, None);
        // one cancel, submit truncated
        assert_eq!(actions.cancel.len(), 1);
        assert_eq!(actions.submit.len(), 0);
    }
}
