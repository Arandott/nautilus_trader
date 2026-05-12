// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
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

//! Experimental L2-specialized order book structures and adapters.

use std::{collections::BTreeMap, fmt::Display};

use nautilus_core::UnixNanos;

use super::aggregation::pre_process_order;
use crate::{
    data::{BookOrder, OrderBookDelta, OrderBookDeltas, OrderBookDepth10},
    enums::{BookAction, BookType, OrderSide, OrderSideSpecified, RecordFlag},
    identifiers::InstrumentId,
    orderbook::{BookIntegrityError, BookLevel, BookPrice, OrderBook},
    types::{Price, Quantity},
};

/// Internal implementation choice for L2-MBP order books.
///
/// `BookType` remains the market-data semantic. This enum only selects the
/// backing data structure used by the stable `OrderBook` facade.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum L2BookBackendKind {
    /// Existing generic `BookLadder` implementation.
    #[default]
    Generic = 0,
    /// Price-level tree implementation.
    Tree = 1,
    /// Sorted-vector implementation (kept experimental).
    Vec = 2,
    /// Sparse tick-grid implementation (kept experimental).
    Grid = 3,
}

impl L2BookBackendKind {
    /// Parse the FFI representation used by Cython/Python.
    #[must_use]
    pub const fn from_u8(value: u8) -> Self {
        match value {
            1 => Self::Tree,
            2 => Self::Vec,
            3 => Self::Grid,
            _ => Self::Generic,
        }
    }

    /// Return the FFI representation used by Cython/Python.
    #[must_use]
    pub const fn as_u8(self) -> u8 {
        self as u8
    }

    /// Return the stable config spelling for the backend.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Generic => "generic",
            Self::Tree => "tree",
            Self::Vec => "vec",
            Self::Grid => "grid",
        }
    }
}

/// Shared L2 operations used by benchmark and replay harnesses.
pub trait L2BookOps: std::fmt::Debug + Sized {
    /// Human-readable label for reporting/benchmark naming.
    const BOOK_LABEL: &'static str;

    /// Create a new L2-MBP book for the given instrument.
    fn new_l2(instrument_id: InstrumentId) -> Self;

    /// Returns the instrument ID tracked by the book.
    fn instrument_id(&self) -> InstrumentId;

    /// Returns the high-water-mark sequence.
    fn sequence(&self) -> u64;

    /// Returns the high-water-mark event timestamp.
    fn ts_last(&self) -> UnixNanos;

    /// Returns the number of updates applied to the book.
    fn update_count(&self) -> u64;

    /// Resets the book to its initial empty state.
    fn reset(&mut self);

    /// Applies a single delta without instrument validation.
    fn apply_delta_unchecked(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError>;

    /// Applies a single delta with instrument validation.
    fn apply_delta(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError> {
        if delta.instrument_id != self.instrument_id() {
            return Err(BookIntegrityError::InstrumentMismatch(
                self.instrument_id(),
                delta.instrument_id,
            ));
        }

        self.apply_delta_unchecked(delta)
    }

    /// Applies multiple deltas with instrument validation.
    fn apply_deltas(&mut self, deltas: &OrderBookDeltas) -> Result<(), BookIntegrityError> {
        if deltas.instrument_id != self.instrument_id() {
            return Err(BookIntegrityError::InstrumentMismatch(
                self.instrument_id(),
                deltas.instrument_id,
            ));
        }

        self.apply_deltas_unchecked(deltas)
    }

    /// Applies multiple deltas without instrument validation.
    fn apply_deltas_unchecked(
        &mut self,
        deltas: &OrderBookDeltas,
    ) -> Result<(), BookIntegrityError> {
        for delta in &deltas.deltas {
            self.apply_delta_unchecked(delta)?;
        }

        Ok(())
    }

    /// Returns the best bid price, if present.
    fn best_bid_price(&self) -> Option<Price>;

    /// Returns the best ask price, if present.
    fn best_ask_price(&self) -> Option<Price>;

    /// Returns the best bid size, if present.
    fn best_bid_size(&self) -> Option<Quantity>;

    /// Returns the best ask size, if present.
    fn best_ask_size(&self) -> Option<Quantity>;

    /// Returns the first `depth` levels for the given side.
    fn top_n_levels(&self, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)>;

    /// Returns a simple checksum of the top bid and ask levels without forcing callers to allocate.
    fn query_depth_checksum(&self, depth: usize) -> ((i128, u128), (i128, u128)) {
        let bids = self.top_n_levels(OrderSide::Buy, depth).into_iter().fold(
            (0_i128, 0_u128),
            |(price_acc, size_acc), (price, size)| {
                (price_acc + price.raw as i128, size_acc + size.raw as u128)
            },
        );

        let asks = self.top_n_levels(OrderSide::Sell, depth).into_iter().fold(
            (0_i128, 0_u128),
            |(price_acc, size_acc), (price, size)| {
                (price_acc + price.raw as i128, size_acc + size.raw as u128)
            },
        );

        (bids, asks)
    }
}

/// A price-level-oriented experimental L2-MBP order book.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct L2TreeBook {
    /// The instrument ID for the order book.
    pub instrument_id: InstrumentId,
    /// The last event sequence number for the order book.
    pub sequence: u64,
    /// The timestamp of the last event applied to the order book.
    pub ts_last: UnixNanos,
    /// The current count of updates applied to the order book.
    pub update_count: u64,
    pub(crate) bids: BTreeMap<BookPrice, Quantity>,
    pub(crate) asks: BTreeMap<BookPrice, Quantity>,
}

impl Display for L2TreeBook {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}(instrument_id={}, book_type=L2_MBP, update_count={})",
            stringify!(L2TreeBook),
            self.instrument_id,
            self.update_count,
        )
    }
}

impl L2TreeBook {
    /// Creates a new experimental L2 tree book.
    #[must_use]
    pub fn new(instrument_id: InstrumentId) -> Self {
        Self {
            instrument_id,
            sequence: 0,
            ts_last: UnixNanos::default(),
            update_count: 0,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
        }
    }

    fn levels(&self, side: OrderSideSpecified) -> &BTreeMap<BookPrice, Quantity> {
        match side {
            OrderSideSpecified::Buy => &self.bids,
            OrderSideSpecified::Sell => &self.asks,
        }
    }

    fn levels_mut(&mut self, side: OrderSideSpecified) -> &mut BTreeMap<BookPrice, Quantity> {
        match side {
            OrderSideSpecified::Buy => &mut self.bids,
            OrderSideSpecified::Sell => &mut self.asks,
        }
    }

    /// Resets the book to its initial empty state.
    pub fn reset(&mut self) {
        self.bids.clear();
        self.asks.clear();
        self.sequence = 0;
        self.ts_last = UnixNanos::default();
        self.update_count = 0;
    }

    pub(crate) fn upsert_level(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        size: Quantity,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        self.levels_mut(side)
            .insert(BookPrice::new(price, side), size);
        self.increment(sequence, ts_event);
    }

    pub(crate) fn delete_level(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        self.levels_mut(side).remove(&BookPrice::new(price, side));
        self.increment(sequence, ts_event);
    }

    pub(crate) fn clear(&mut self, sequence: u64, ts_event: UnixNanos) {
        self.bids.clear();
        self.asks.clear();
        self.increment(sequence, ts_event);
    }

    pub(crate) fn clear_bids(&mut self, sequence: u64, ts_event: UnixNanos) {
        self.bids.clear();
        self.increment(sequence, ts_event);
    }

    pub(crate) fn clear_asks(&mut self, sequence: u64, ts_event: UnixNanos) {
        self.asks.clear();
        self.increment(sequence, ts_event);
    }

    fn best_level(&self, side: OrderSideSpecified) -> Option<(Price, Quantity)> {
        self.levels(side)
            .iter()
            .next()
            .map(|(price, size)| (price.value, *size))
    }

    /// Returns true if the bid side has any price levels.
    #[must_use]
    pub fn has_bid(&self) -> bool {
        !self.bids.is_empty()
    }

    /// Returns true if the ask side has any price levels.
    #[must_use]
    pub fn has_ask(&self) -> bool {
        !self.asks.is_empty()
    }

    /// Returns the best bid price, if present.
    #[must_use]
    pub fn best_bid_price(&self) -> Option<Price> {
        self.best_level(OrderSideSpecified::Buy)
            .map(|(price, _)| price)
    }

    /// Returns the best ask price, if present.
    #[must_use]
    pub fn best_ask_price(&self) -> Option<Price> {
        self.best_level(OrderSideSpecified::Sell)
            .map(|(price, _)| price)
    }

    /// Returns the best bid size, if present.
    #[must_use]
    pub fn best_bid_size(&self) -> Option<Quantity> {
        self.best_level(OrderSideSpecified::Buy)
            .map(|(_, size)| size)
    }

    /// Returns the best ask size, if present.
    #[must_use]
    pub fn best_ask_size(&self) -> Option<Quantity> {
        self.best_level(OrderSideSpecified::Sell)
            .map(|(_, size)| size)
    }

    /// Returns the first `depth` levels for the given side.
    #[must_use]
    pub fn top_n_levels(&self, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)> {
        let levels = match side {
            OrderSide::Buy => &self.bids,
            OrderSide::Sell => &self.asks,
            OrderSide::NoOrderSide => return Vec::new(),
        };

        levels
            .iter()
            .take(depth)
            .map(|(price, size)| (price.value, *size))
            .collect()
    }

    /// Returns bid levels as compatibility `BookLevel` values.
    #[must_use]
    pub fn bids_as_book_levels(&self, depth: Option<usize>) -> Vec<BookLevel> {
        self.book_levels(OrderSideSpecified::Buy, depth)
    }

    /// Returns ask levels as compatibility `BookLevel` values.
    #[must_use]
    pub fn asks_as_book_levels(&self, depth: Option<usize>) -> Vec<BookLevel> {
        self.book_levels(OrderSideSpecified::Sell, depth)
    }

    fn book_levels(&self, side: OrderSideSpecified, depth: Option<usize>) -> Vec<BookLevel> {
        self.levels(side)
            .iter()
            .take(depth.unwrap_or(usize::MAX))
            .map(|(price, size)| Self::book_level_from_parts(side, price.value, *size))
            .collect()
    }

    fn book_level_from_parts(side: OrderSideSpecified, price: Price, size: Quantity) -> BookLevel {
        let order_side = match side {
            OrderSideSpecified::Buy => OrderSide::Buy,
            OrderSideSpecified::Sell => OrderSide::Sell,
        };
        let order = BookOrder::new(order_side, price, size, 0);
        BookLevel::from_order(pre_process_order(BookType::L2_MBP, order, 0))
    }

    /// Returns bid levels down to and including `price`.
    #[must_use]
    pub fn bids_down_to(&self, price: Price) -> Vec<BookLevel> {
        let bound = BookPrice::new(price, OrderSideSpecified::Buy);
        self.bids
            .range(..=bound)
            .map(|(book_price, size)| {
                Self::book_level_from_parts(OrderSideSpecified::Buy, book_price.value, *size)
            })
            .collect()
    }

    /// Returns ask levels up to and including `price`.
    #[must_use]
    pub fn asks_up_to(&self, price: Price) -> Vec<BookLevel> {
        let bound = BookPrice::new(price, OrderSideSpecified::Sell);
        self.asks
            .range(..=bound)
            .map(|(book_price, size)| {
                Self::book_level_from_parts(OrderSideSpecified::Sell, book_price.value, *size)
            })
            .collect()
    }

    /// Replaces current state with a depth10 snapshot.
    ///
    /// # Errors
    ///
    /// Returns an error if the depth belongs to another instrument.
    pub fn apply_depth(&mut self, depth: &OrderBookDepth10) -> Result<(), BookIntegrityError> {
        if depth.instrument_id != self.instrument_id {
            return Err(BookIntegrityError::InstrumentMismatch(
                self.instrument_id,
                depth.instrument_id,
            ));
        }
        self.apply_depth_unchecked(depth)
    }

    /// Replaces current state with a depth10 snapshot without instrument validation.
    pub fn apply_depth_unchecked(
        &mut self,
        depth: &OrderBookDepth10,
    ) -> Result<(), BookIntegrityError> {
        self.bids.clear();
        self.asks.clear();

        for order in depth.bids {
            if order.side == OrderSide::NoOrderSide || !order.size.is_positive() {
                continue;
            }
            if order.side != OrderSide::Buy {
                log::warn!(
                    "Skipping bid order with wrong side {:?} (instrument_id={})",
                    order.side,
                    self.instrument_id
                );
                continue;
            }
            self.bids.insert(
                BookPrice::new(order.price, OrderSideSpecified::Buy),
                order.size,
            );
        }

        for order in depth.asks {
            if order.side == OrderSide::NoOrderSide || !order.size.is_positive() {
                continue;
            }
            if order.side != OrderSide::Sell {
                log::warn!(
                    "Skipping ask order with wrong side {:?} (instrument_id={})",
                    order.side,
                    self.instrument_id
                );
                continue;
            }
            self.asks.insert(
                BookPrice::new(order.price, OrderSideSpecified::Sell),
                order.size,
            );
        }

        self.increment(depth.sequence, depth.ts_event);
        Ok(())
    }

    /// Creates an L2 snapshot as `OrderBookDeltas`.
    #[must_use]
    pub fn to_deltas(&self, ts_event: UnixNanos, ts_init: UnixNanos) -> OrderBookDeltas {
        let total_orders = self.bids.len() + self.asks.len();
        let mut deltas = Vec::with_capacity(total_orders + 1);
        let mut clear = OrderBookDelta::clear(self.instrument_id, self.sequence, ts_event, ts_init);

        if total_orders == 0 {
            clear.flags |= RecordFlag::F_LAST as u8;
        }
        deltas.push(clear);

        let mut order_count = 0;
        for (book_price, size) in &self.bids {
            order_count += 1;
            let flags = if order_count == total_orders {
                RecordFlag::F_SNAPSHOT as u8 | RecordFlag::F_LAST as u8
            } else {
                RecordFlag::F_SNAPSHOT as u8
            };
            deltas.push(self.snapshot_delta(
                OrderSide::Buy,
                book_price.value,
                *size,
                flags,
                ts_event,
                ts_init,
            ));
        }

        for (book_price, size) in &self.asks {
            order_count += 1;
            let flags = if order_count == total_orders {
                RecordFlag::F_SNAPSHOT as u8 | RecordFlag::F_LAST as u8
            } else {
                RecordFlag::F_SNAPSHOT as u8
            };
            deltas.push(self.snapshot_delta(
                OrderSide::Sell,
                book_price.value,
                *size,
                flags,
                ts_event,
                ts_init,
            ));
        }

        OrderBookDeltas::new(self.instrument_id, deltas)
    }

    fn snapshot_delta(
        &self,
        side: OrderSide,
        price: Price,
        size: Quantity,
        flags: u8,
        ts_event: UnixNanos,
        ts_init: UnixNanos,
    ) -> OrderBookDelta {
        let order = pre_process_order(
            BookType::L2_MBP,
            BookOrder::new(side, price, size, 0),
            flags,
        );
        OrderBookDelta::new(
            self.instrument_id,
            BookAction::Add,
            order,
            flags,
            self.sequence,
            ts_event,
            ts_init,
        )
    }

    /// Returns cumulative quantity available at or better than `price`.
    #[must_use]
    pub fn get_quantity_for_price(&self, price: Price, order_side: OrderSide) -> f64 {
        let (side, levels) = match order_side.as_specified() {
            OrderSideSpecified::Buy => (OrderSideSpecified::Buy, &self.asks),
            OrderSideSpecified::Sell => (OrderSideSpecified::Sell, &self.bids),
        };

        let mut matched_size = 0.0;
        for (book_price, size) in levels {
            match side {
                OrderSideSpecified::Buy if book_price.value > price => break,
                OrderSideSpecified::Sell if book_price.value < price => break,
                _ => matched_size += size.as_f64(),
            }
        }
        matched_size
    }

    /// Returns quantity at exactly one crossed price level.
    #[must_use]
    pub fn get_quantity_at_level(
        &self,
        price: Price,
        order_side: OrderSide,
        size_precision: u8,
    ) -> Quantity {
        let (levels, book_side) = match order_side.as_specified() {
            OrderSideSpecified::Buy => (&self.asks, OrderSideSpecified::Sell),
            OrderSideSpecified::Sell => (&self.bids, OrderSideSpecified::Buy),
        };

        levels
            .get(&BookPrice::new(price, book_side))
            .copied()
            .unwrap_or_else(|| Quantity::zero(size_precision))
    }

    /// Simulates fills against the opposite side of the L2 book.
    #[must_use]
    pub fn simulate_fills(&self, order: &BookOrder) -> Vec<(Price, Quantity)> {
        let (is_reversed, levels) = match order.side.as_specified() {
            OrderSideSpecified::Buy => (false, &self.asks),
            OrderSideSpecified::Sell => (true, &self.bids),
        };
        let mut fills = Vec::new();
        let mut cumulative = Quantity::zero(order.size.precision);

        for (book_price, size) in levels {
            if (is_reversed && book_price.value < order.price)
                || (!is_reversed && book_price.value > order.price)
            {
                break;
            }

            if cumulative + *size >= order.size {
                let remainder = order.size - cumulative;
                if remainder.is_positive() {
                    fills.push((book_price.value, remainder));
                }
                return fills;
            }

            fills.push((book_price.value, *size));
            cumulative = cumulative + *size;
        }

        fills
    }

    /// Returns all price levels crossed by an order at the given price.
    #[must_use]
    pub fn get_all_crossed_levels(
        &self,
        order_side: OrderSide,
        price: Price,
        _size_precision: u8,
    ) -> Vec<(Price, Quantity)> {
        let (side, levels) = match order_side.as_specified() {
            OrderSideSpecified::Buy => (OrderSideSpecified::Buy, &self.asks),
            OrderSideSpecified::Sell => (OrderSideSpecified::Sell, &self.bids),
        };

        let mut result = Vec::new();
        for (book_price, size) in levels {
            match side {
                OrderSideSpecified::Buy if book_price.value > price => break,
                OrderSideSpecified::Sell if book_price.value < price => break,
                _ => result.push((book_price.value, *size)),
            }
        }
        result
    }

    /// Calculates the average price to fill a specified quantity.
    #[must_use]
    pub fn get_avg_px_for_quantity(&self, qty: Quantity, order_side: OrderSide) -> f64 {
        let levels = match order_side.as_specified() {
            OrderSideSpecified::Buy => &self.asks,
            OrderSideSpecified::Sell => &self.bids,
        };
        let mut cumulative_size_raw = 0;
        let mut cumulative_value = 0.0;

        for (book_price, size) in levels {
            let size_this_level = size.raw.min(qty.raw - cumulative_size_raw);
            cumulative_size_raw += size_this_level;
            cumulative_value += book_price.value.as_f64() * size_this_level as f64;

            if cumulative_size_raw >= qty.raw {
                break;
            }
        }

        if cumulative_size_raw == 0 {
            0.0
        } else {
            cumulative_value / cumulative_size_raw as f64
        }
    }

    /// Calculates the worst price touched to fill a specified quantity.
    #[must_use]
    pub fn get_worst_px_for_quantity(&self, qty: Quantity, order_side: OrderSide) -> Option<Price> {
        let levels = match order_side.as_specified() {
            OrderSideSpecified::Buy => &self.asks,
            OrderSideSpecified::Sell => &self.bids,
        };
        let mut cumulative_size_raw = 0;
        let mut worst_price = None;

        for (book_price, size) in levels {
            let size_this_level = size.raw.min(qty.raw - cumulative_size_raw);
            if size_this_level == 0 {
                continue;
            }
            cumulative_size_raw += size_this_level;
            worst_price = Some(book_price.value);

            if cumulative_size_raw >= qty.raw {
                break;
            }
        }

        if cumulative_size_raw == 0 {
            None
        } else {
            worst_price
        }
    }

    fn resolve_no_side_by_price(&self, mut order: BookOrder) -> Option<BookOrder> {
        let bid_price = BookPrice::new(order.price, OrderSideSpecified::Buy);
        if self.bids.contains_key(&bid_price) {
            order.side = OrderSide::Buy;
            return Some(order);
        }

        let ask_price = BookPrice::new(order.price, OrderSideSpecified::Sell);
        if self.asks.contains_key(&ask_price) {
            order.side = OrderSide::Sell;
            return Some(order);
        }

        None
    }

    fn increment(&mut self, sequence: u64, ts_event: UnixNanos) {
        if sequence > 0 && sequence < self.sequence {
            log::warn!(
                "Out-of-order update: sequence {} < {} (instrument_id={})",
                sequence,
                self.sequence,
                self.instrument_id
            );
        }

        if ts_event < self.ts_last {
            log::warn!(
                "Out-of-order update: ts_event {} < {} (instrument_id={})",
                ts_event,
                self.ts_last,
                self.instrument_id
            );
        }

        if self.update_count == u64::MAX {
            debug_assert!(
                self.update_count < u64::MAX,
                "Update count at u64::MAX limit (about to overflow): {}",
                self.update_count
            );
            log::warn!(
                "Update count at u64::MAX: {} (instrument_id={})",
                self.update_count,
                self.instrument_id
            );
        }

        self.sequence = sequence.max(self.sequence);
        self.ts_last = ts_event.max(self.ts_last);
        self.update_count = self.update_count.saturating_add(1);
    }
}

impl L2BookOps for L2TreeBook {
    const BOOK_LABEL: &'static str = "l2tree";

    fn new_l2(instrument_id: InstrumentId) -> Self {
        Self::new(instrument_id)
    }

    fn instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    fn sequence(&self) -> u64 {
        self.sequence
    }

    fn ts_last(&self) -> UnixNanos {
        self.ts_last
    }

    fn update_count(&self) -> u64 {
        self.update_count
    }

    fn reset(&mut self) {
        L2TreeBook::reset(self);
    }

    fn apply_delta_unchecked(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError> {
        let mut order = delta.order;

        if order.side == OrderSide::NoOrderSide {
            match delta.action {
                BookAction::Add => return Err(BookIntegrityError::NoOrderSide),
                BookAction::Update | BookAction::Delete if order.order_id != 0 => {
                    if let Some(resolved) = self.resolve_no_side_by_price(order) {
                        order = resolved;
                    } else {
                        log::debug!(
                            "Skipping {:?} for unknown order_id={}",
                            delta.action,
                            order.order_id
                        );
                        return Ok(());
                    }
                }
                BookAction::Update | BookAction::Delete => {
                    return Err(BookIntegrityError::NoOrderSide);
                }
                BookAction::Clear => {}
            }
        }

        let sequence = delta.sequence;
        let ts_event = delta.ts_event;

        match delta.action {
            BookAction::Add => {
                if !order.size.is_positive() {
                    self.increment(sequence, ts_event);
                    return Ok(());
                }
                self.upsert_level(
                    order.side.as_specified(),
                    order.price,
                    order.size,
                    sequence,
                    ts_event,
                );
            }
            BookAction::Update => {
                if !order.size.is_positive() {
                    self.delete_level(order.side.as_specified(), order.price, sequence, ts_event);
                    return Ok(());
                }
                self.upsert_level(
                    order.side.as_specified(),
                    order.price,
                    order.size,
                    sequence,
                    ts_event,
                );
            }
            BookAction::Delete => {
                self.delete_level(order.side.as_specified(), order.price, sequence, ts_event);
            }
            BookAction::Clear => self.clear(sequence, ts_event),
        }

        Ok(())
    }

    fn best_bid_price(&self) -> Option<Price> {
        L2TreeBook::best_bid_price(self)
    }

    fn best_ask_price(&self) -> Option<Price> {
        L2TreeBook::best_ask_price(self)
    }

    fn best_bid_size(&self) -> Option<Quantity> {
        L2TreeBook::best_bid_size(self)
    }

    fn best_ask_size(&self) -> Option<Quantity> {
        L2TreeBook::best_ask_size(self)
    }

    fn top_n_levels(&self, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)> {
        L2TreeBook::top_n_levels(self, side, depth)
    }

    fn query_depth_checksum(&self, depth: usize) -> ((i128, u128), (i128, u128)) {
        let bids = self.bids.iter().take(depth).fold(
            (0_i128, 0_u128),
            |(price_acc, size_acc), (price, size)| {
                (
                    price_acc + price.value.raw as i128,
                    size_acc + size.raw as u128,
                )
            },
        );

        let asks = self.asks.iter().take(depth).fold(
            (0_i128, 0_u128),
            |(price_acc, size_acc), (price, size)| {
                (
                    price_acc + price.value.raw as i128,
                    size_acc + size.raw as u128,
                )
            },
        );

        (bids, asks)
    }
}

impl L2BookOps for OrderBook {
    const BOOK_LABEL: &'static str = "baseline";

    fn new_l2(instrument_id: InstrumentId) -> Self {
        Self::new(instrument_id, BookType::L2_MBP)
    }

    fn instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    fn sequence(&self) -> u64 {
        self.sequence
    }

    fn ts_last(&self) -> UnixNanos {
        self.ts_last
    }

    fn update_count(&self) -> u64 {
        self.update_count
    }

    fn reset(&mut self) {
        Self::reset(self);
    }

    fn apply_delta_unchecked(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError> {
        Self::apply_delta_unchecked(self, delta)
    }

    fn best_bid_price(&self) -> Option<Price> {
        Self::best_bid_price(self)
    }

    fn best_ask_price(&self) -> Option<Price> {
        Self::best_ask_price(self)
    }

    fn best_bid_size(&self) -> Option<Quantity> {
        Self::best_bid_size(self)
    }

    fn best_ask_size(&self) -> Option<Quantity> {
        Self::best_ask_size(self)
    }

    fn top_n_levels(&self, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)> {
        let levels: Box<dyn Iterator<Item = _>> = match side {
            OrderSide::Buy => Box::new(self.bids(Some(depth))),
            OrderSide::Sell => Box::new(self.asks(Some(depth))),
            OrderSide::NoOrderSide => return Vec::new(),
        };

        levels
            .map(|level| {
                let precision = level.first().map(|order| order.size.precision).unwrap_or(0);
                (
                    level.price.value,
                    Quantity::from_raw(level.size_raw(), precision),
                )
            })
            .collect()
    }

    fn query_depth_checksum(&self, depth: usize) -> ((i128, u128), (i128, u128)) {
        let bids = self
            .bids(Some(depth))
            .fold((0_i128, 0_u128), |(price_acc, size_acc), level| {
                (
                    price_acc + level.price.value.raw as i128,
                    size_acc + level.size_raw() as u128,
                )
            });

        let asks = self
            .asks(Some(depth))
            .fold((0_i128, 0_u128), |(price_acc, size_acc), level| {
                (
                    price_acc + level.price.value.raw as i128,
                    size_acc + level.size_raw() as u128,
                )
            });

        (bids, asks)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        data::{BookOrder, OrderBookDelta, OrderBookDepth10},
        enums::BookType,
    };

    const PRICE_PRECISION: u8 = 1;
    const SIZE_PRECISION: u8 = 3;

    fn instrument_id() -> InstrumentId {
        InstrumentId::from("BTCUSDT.BINANCE")
    }

    fn delta(
        action: BookAction,
        side: OrderSide,
        price: Price,
        size: Quantity,
        sequence: u64,
    ) -> OrderBookDelta {
        OrderBookDelta::new(
            instrument_id(),
            action,
            BookOrder::new(side, price, size, sequence),
            0,
            sequence,
            sequence.into(),
            sequence.into(),
        )
    }

    fn top_n_baseline(book: &OrderBook, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)> {
        book.top_n_levels(side, depth)
    }

    fn assert_parity(baseline: &OrderBook, candidate: &L2TreeBook) {
        assert_eq!(baseline.best_bid_price(), candidate.best_bid_price());
        assert_eq!(baseline.best_ask_price(), candidate.best_ask_price());
        assert_eq!(baseline.best_bid_size(), candidate.best_bid_size());
        assert_eq!(baseline.best_ask_size(), candidate.best_ask_size());
        assert_eq!(baseline.sequence, candidate.sequence);
        assert_eq!(baseline.ts_last, candidate.ts_last);
        assert_eq!(baseline.update_count, candidate.update_count);
        assert_eq!(
            top_n_baseline(baseline, OrderSide::Buy, 10),
            candidate.top_n_levels(OrderSide::Buy, 10)
        );
        assert_eq!(
            top_n_baseline(baseline, OrderSide::Sell, 10),
            candidate.top_n_levels(OrderSide::Sell, 10)
        );
    }

    #[test]
    fn test_l2_tree_book_matches_baseline_for_basic_sequence() {
        let deltas = vec![
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(1.5, SIZE_PRECISION),
                1,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.1, PRICE_PRECISION),
                Quantity::new(2.5, SIZE_PRECISION),
                2,
            ),
            delta(
                BookAction::Update,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(3.0, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.9, PRICE_PRECISION),
                Quantity::new(4.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Sell,
                Price::new(100.1, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                5,
            ),
            OrderBookDelta::clear(instrument_id(), 6, 6.into(), 6.into()),
        ];

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2TreeBook::new(instrument_id());

        for delta in &deltas {
            baseline.apply_delta(delta).unwrap();
            candidate.apply_delta(delta).unwrap();
            assert_parity(&baseline, &candidate);
        }
    }

    #[test]
    fn test_update_missing_level_upserts_like_baseline() {
        let delta = delta(
            BookAction::Update,
            OrderSide::Buy,
            Price::new(99.8, PRICE_PRECISION),
            Quantity::new(5.0, SIZE_PRECISION),
            1,
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2TreeBook::new(instrument_id());

        baseline.apply_delta(&delta).unwrap();
        candidate.apply_delta(&delta).unwrap();

        assert_parity(&baseline, &candidate);
    }

    #[test]
    fn test_delete_missing_level_is_noop_like_baseline() {
        let delta = delta(
            BookAction::Delete,
            OrderSide::Buy,
            Price::new(101.0, PRICE_PRECISION),
            Quantity::new(1.0, SIZE_PRECISION),
            1,
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2TreeBook::new(instrument_id());

        baseline.apply_delta(&delta).unwrap();
        candidate.apply_delta(&delta).unwrap();

        assert_parity(&baseline, &candidate);
    }

    #[test]
    fn test_instrument_mismatch_returns_error() {
        let mut candidate = L2TreeBook::new(instrument_id());
        let delta = OrderBookDelta::new(
            InstrumentId::from("ETHUSDT.BINANCE"),
            BookAction::Add,
            BookOrder::new(
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                1,
            ),
            0,
            1,
            1.into(),
            1.into(),
        );

        let result = candidate.apply_delta(&delta);

        assert_eq!(
            result,
            Err(BookIntegrityError::InstrumentMismatch(
                instrument_id(),
                InstrumentId::from("ETHUSDT.BINANCE")
            ))
        );
    }

    #[test]
    fn test_no_order_side_returns_error_like_baseline() {
        let delta = delta(
            BookAction::Add,
            OrderSide::NoOrderSide,
            Price::new(100.0, PRICE_PRECISION),
            Quantity::new(1.0, SIZE_PRECISION),
            1,
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2TreeBook::new(instrument_id());

        let baseline_result = baseline.apply_delta(&delta);
        let candidate_result = candidate.apply_delta(&delta);

        assert_eq!(baseline_result, Err(BookIntegrityError::NoOrderSide));
        assert_eq!(candidate_result, Err(BookIntegrityError::NoOrderSide));
    }

    #[test]
    fn test_unknown_no_side_update_is_skipped_like_baseline() {
        let delta = OrderBookDelta::new(
            instrument_id(),
            BookAction::Update,
            BookOrder::new(
                OrderSide::NoOrderSide,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                42,
            ),
            0,
            1,
            1.into(),
            1.into(),
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2TreeBook::new(instrument_id());

        let baseline_result = baseline.apply_delta(&delta);
        let candidate_result = candidate.apply_delta(&delta);

        assert_eq!(baseline_result, Ok(()));
        assert_eq!(candidate_result, Ok(()));
        assert_parity(&baseline, &candidate);
    }

    #[test]
    fn test_order_book_tree_backend_facade_matches_generic_production_queries() {
        let deltas = vec![
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(3.0, SIZE_PRECISION),
                1,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.9, PRICE_PRECISION),
                Quantity::new(2.0, SIZE_PRECISION),
                2,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.1, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.2, PRICE_PRECISION),
                Quantity::new(5.0, SIZE_PRECISION),
                4,
            ),
        ];

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = OrderBook::new_with_l2_backend(
            instrument_id(),
            BookType::L2_MBP,
            L2BookBackendKind::Tree,
        );

        assert_eq!(candidate.l2_backend(), L2BookBackendKind::Tree);

        for delta in &deltas {
            baseline.apply_delta(delta).unwrap();
            candidate.apply_delta(delta).unwrap();
        }

        assert_eq!(baseline.best_bid_price(), candidate.best_bid_price());
        assert_eq!(baseline.best_ask_price(), candidate.best_ask_price());
        assert_eq!(baseline.best_bid_size(), candidate.best_bid_size());
        assert_eq!(baseline.best_ask_size(), candidate.best_ask_size());
        assert_eq!(
            baseline.get_quantity_at_level(
                Price::new(100.1, PRICE_PRECISION),
                OrderSide::Buy,
                SIZE_PRECISION
            ),
            candidate.get_quantity_at_level(
                Price::new(100.1, PRICE_PRECISION),
                OrderSide::Buy,
                SIZE_PRECISION
            )
        );
        assert_eq!(
            baseline.get_all_crossed_levels(
                OrderSide::Buy,
                Price::new(100.2, PRICE_PRECISION),
                SIZE_PRECISION
            ),
            candidate.get_all_crossed_levels(
                OrderSide::Buy,
                Price::new(100.2, PRICE_PRECISION),
                SIZE_PRECISION
            )
        );

        let order = BookOrder::new(
            OrderSide::Buy,
            Price::new(100.2, PRICE_PRECISION),
            Quantity::new(4.0, SIZE_PRECISION),
            99,
        );
        assert_eq!(
            baseline.simulate_fills(&order),
            candidate.simulate_fills(&order)
        );

        let snapshot = candidate.to_deltas(10.into(), 10.into());
        let mut replayed = OrderBook::new(instrument_id(), BookType::L2_MBP);
        replayed.apply_deltas(&snapshot).unwrap();
        assert_eq!(candidate.best_bid_price(), replayed.best_bid_price());
        assert_eq!(candidate.best_ask_price(), replayed.best_ask_price());
        assert_eq!(
            candidate.top_n_levels(OrderSide::Buy, 10),
            replayed.top_n_levels(OrderSide::Buy, 10)
        );
        assert_eq!(
            candidate.top_n_levels(OrderSide::Sell, 10),
            replayed.top_n_levels(OrderSide::Sell, 10)
        );
    }

    #[test]
    fn test_order_book_tree_backend_apply_depth_matches_generic() {
        let mut bids = [BookOrder::default(); 10];
        bids[0] = BookOrder::new(
            OrderSide::Buy,
            Price::new(100.0, PRICE_PRECISION),
            Quantity::new(3.0, SIZE_PRECISION),
            1,
        );
        bids[1] = BookOrder::new(
            OrderSide::Buy,
            Price::new(99.9, PRICE_PRECISION),
            Quantity::new(2.0, SIZE_PRECISION),
            2,
        );

        let mut asks = [BookOrder::default(); 10];
        asks[0] = BookOrder::new(
            OrderSide::Sell,
            Price::new(100.1, PRICE_PRECISION),
            Quantity::new(1.0, SIZE_PRECISION),
            3,
        );
        asks[1] = BookOrder::new(
            OrderSide::Sell,
            Price::new(100.2, PRICE_PRECISION),
            Quantity::new(5.0, SIZE_PRECISION),
            4,
        );

        let depth = OrderBookDepth10::new(
            instrument_id(),
            bids,
            asks,
            [1; 10],
            [1; 10],
            0,
            42,
            42.into(),
            42.into(),
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = OrderBook::new_with_l2_backend(
            instrument_id(),
            BookType::L2_MBP,
            L2BookBackendKind::Tree,
        );

        baseline.apply_depth(&depth).unwrap();
        candidate.apply_depth(&depth).unwrap();

        assert_eq!(baseline.best_bid_price(), candidate.best_bid_price());
        assert_eq!(baseline.best_ask_price(), candidate.best_ask_price());
        assert_eq!(
            baseline.top_n_levels(OrderSide::Buy, 10),
            candidate.top_n_levels(OrderSide::Buy, 10)
        );
        assert_eq!(
            baseline.top_n_levels(OrderSide::Sell, 10),
            candidate.top_n_levels(OrderSide::Sell, 10)
        );
        assert_eq!(candidate.sequence, 42);
        assert_eq!(candidate.update_count, 1);
    }
}
