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

//! Contiguous L2-MBP order book backed by sorted `Vec` price levels.

use std::{fmt::Display, mem::size_of};

use nautilus_core::UnixNanos;
use serde::Serialize;

use crate::{
    data::OrderBookDelta,
    enums::{BookAction, OrderSide, OrderSideSpecified},
    identifiers::InstrumentId,
    orderbook::{BookIntegrityError, L2BookOps},
    types::{Price, Quantity, price::PriceRaw, quantity::QuantityRaw},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct VecLevel {
    price_raw: PriceRaw,
    size_raw: QuantityRaw,
}

type Level = VecLevel;

impl VecLevel {
    fn new(price: Price, size: Quantity) -> Self {
        Self {
            price_raw: price.raw,
            size_raw: size.raw,
        }
    }

    fn price(self, precision: u8) -> Price {
        Price::from_raw(self.price_raw, precision)
    }

    fn size(self, precision: u8) -> Quantity {
        Quantity::from_raw(self.size_raw, precision)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2VecLayoutStats {
    pub price_raw_size_bytes: usize,
    pub quantity_raw_size_bytes: usize,
    pub price_size_bytes: usize,
    pub quantity_size_bytes: usize,
    pub level_size_bytes: usize,
    pub vec_level_size_bytes: usize,
    pub l2_vec_book_size_bytes: usize,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2VecSideDiagnosticSnapshot {
    pub active_levels: u64,
    pub reserved_levels: u64,
    pub spare_capacity: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2VecDiagnosticSnapshot {
    pub bids: L2VecSideDiagnosticSnapshot,
    pub asks: L2VecSideDiagnosticSnapshot,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum L2VecMutationKind {
    AddExisting,
    AddInsertNew,
    AddZeroSizeNoop,
    UpdateExistingSizeChange,
    UpdateExistingRemove,
    UpdateMissingInsert,
    UpdateMissingZeroSizeNoop,
    DeleteExisting,
    DeleteMissing,
    Clear,
    IgnoredUnknownOrder,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct L2VecDeltaProbe {
    pub kind: L2VecMutationKind,
    pub side: Option<OrderSideSpecified>,
    pub len_before: usize,
    pub index: Option<usize>,
    pub shifted_levels: usize,
    pub shifted_bytes: usize,
}

/// A price-level-oriented experimental L2-MBP order book backed by contiguous storage.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct L2VecBook {
    /// The instrument ID for the order book.
    pub instrument_id: InstrumentId,
    /// The last event sequence number for the order book.
    pub sequence: u64,
    /// The timestamp of the last event applied to the order book.
    pub ts_last: UnixNanos,
    /// The current count of updates applied to the order book.
    pub update_count: u64,
    price_precision: u8,
    size_precision: u8,
    bids: Vec<Level>,
    asks: Vec<Level>,
}

impl Display for L2VecBook {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}(instrument_id={}, book_type=L2_MBP, update_count={})",
            stringify!(L2VecBook),
            self.instrument_id,
            self.update_count,
        )
    }
}

impl L2VecBook {
    #[must_use]
    pub fn new(instrument_id: InstrumentId) -> Self {
        Self {
            instrument_id,
            sequence: 0,
            ts_last: UnixNanos::default(),
            update_count: 0,
            price_precision: 0,
            size_precision: 0,
            bids: Vec::new(),
            asks: Vec::new(),
        }
    }

    fn levels(&self, side: OrderSideSpecified) -> &[Level] {
        match side {
            OrderSideSpecified::Buy => &self.bids,
            OrderSideSpecified::Sell => &self.asks,
        }
    }

    fn levels_mut(&mut self, side: OrderSideSpecified) -> &mut Vec<Level> {
        match side {
            OrderSideSpecified::Buy => &mut self.bids,
            OrderSideSpecified::Sell => &mut self.asks,
        }
    }

    #[must_use]
    pub fn diagnostic_layout_stats() -> L2VecLayoutStats {
        L2VecLayoutStats {
            price_raw_size_bytes: size_of::<PriceRaw>(),
            quantity_raw_size_bytes: size_of::<QuantityRaw>(),
            price_size_bytes: size_of::<Price>(),
            quantity_size_bytes: size_of::<Quantity>(),
            level_size_bytes: size_of::<Level>(),
            vec_level_size_bytes: size_of::<Vec<Level>>(),
            l2_vec_book_size_bytes: size_of::<Self>(),
        }
    }

    fn side_snapshot(levels: &[Level], reserved_levels: usize) -> L2VecSideDiagnosticSnapshot {
        let active_levels = levels.len() as u64;
        let reserved_levels = reserved_levels as u64;

        L2VecSideDiagnosticSnapshot {
            active_levels,
            reserved_levels,
            spare_capacity: reserved_levels.saturating_sub(active_levels),
        }
    }

    #[must_use]
    pub fn diagnostic_snapshot(&self) -> L2VecDiagnosticSnapshot {
        L2VecDiagnosticSnapshot {
            bids: Self::side_snapshot(&self.bids, self.bids.capacity()),
            asks: Self::side_snapshot(&self.asks, self.asks.capacity()),
        }
    }

    fn find_level_index(
        levels: &[Level],
        side: OrderSideSpecified,
        price: Price,
    ) -> Result<usize, usize> {
        levels.binary_search_by(|level| match side {
            OrderSideSpecified::Buy => price.raw.cmp(&level.price_raw),
            OrderSideSpecified::Sell => level.price_raw.cmp(&price.raw),
        })
    }

    fn observe_precisions(&mut self, price_precision: u8, size_precision: u8) {
        self.price_precision = self.price_precision.max(price_precision);
        self.size_precision = self.size_precision.max(size_precision);
    }

    fn shifted_bytes(shifted_levels: usize) -> usize {
        shifted_levels.saturating_mul(size_of::<Level>())
    }

    fn probe_side_delta(
        &self,
        side: OrderSideSpecified,
        action: BookAction,
        price: Price,
        size: Quantity,
    ) -> L2VecDeltaProbe {
        let levels = self.levels(side);
        let len_before = levels.len();

        match (action, Self::find_level_index(levels, side, price)) {
            (BookAction::Add, Ok(index)) => {
                if size.raw == 0 {
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::AddZeroSizeNoop,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    }
                } else {
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::AddExisting,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    }
                }
            }
            (BookAction::Add, Err(index)) => {
                if size.raw == 0 {
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::AddZeroSizeNoop,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    }
                } else {
                    let shifted_levels = len_before.saturating_sub(index);
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::AddInsertNew,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels,
                        shifted_bytes: Self::shifted_bytes(shifted_levels),
                    }
                }
            }
            (BookAction::Update, Ok(index)) => {
                if size.raw == 0 {
                    let shifted_levels = len_before.saturating_sub(index + 1);
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::UpdateExistingRemove,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels,
                        shifted_bytes: Self::shifted_bytes(shifted_levels),
                    }
                } else {
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::UpdateExistingSizeChange,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    }
                }
            }
            (BookAction::Update, Err(index)) => {
                if size.raw == 0 {
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::UpdateMissingZeroSizeNoop,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    }
                } else {
                    let shifted_levels = len_before.saturating_sub(index);
                    L2VecDeltaProbe {
                        kind: L2VecMutationKind::UpdateMissingInsert,
                        side: Some(side),
                        len_before,
                        index: Some(index),
                        shifted_levels,
                        shifted_bytes: Self::shifted_bytes(shifted_levels),
                    }
                }
            }
            (BookAction::Delete, Ok(index)) => {
                let shifted_levels = len_before.saturating_sub(index + 1);
                L2VecDeltaProbe {
                    kind: L2VecMutationKind::DeleteExisting,
                    side: Some(side),
                    len_before,
                    index: Some(index),
                    shifted_levels,
                    shifted_bytes: Self::shifted_bytes(shifted_levels),
                }
            }
            (BookAction::Delete, Err(index)) => L2VecDeltaProbe {
                kind: L2VecMutationKind::DeleteMissing,
                side: Some(side),
                len_before,
                index: Some(index),
                shifted_levels: 0,
                shifted_bytes: 0,
            },
            (BookAction::Clear, _) => L2VecDeltaProbe {
                kind: L2VecMutationKind::Clear,
                side: None,
                len_before: self.bids.len() + self.asks.len(),
                index: None,
                shifted_levels: 0,
                shifted_bytes: 0,
            },
        }
    }

    pub fn probe_delta(
        &self,
        delta: &OrderBookDelta,
    ) -> Result<L2VecDeltaProbe, BookIntegrityError> {
        let order = delta.order;

        if order.side == OrderSide::NoOrderSide {
            return match delta.action {
                BookAction::Add => Err(BookIntegrityError::NoOrderSide),
                BookAction::Update | BookAction::Delete if order.order_id != 0 => {
                    Ok(L2VecDeltaProbe {
                        kind: L2VecMutationKind::IgnoredUnknownOrder,
                        side: None,
                        len_before: 0,
                        index: None,
                        shifted_levels: 0,
                        shifted_bytes: 0,
                    })
                }
                BookAction::Update | BookAction::Delete => Err(BookIntegrityError::NoOrderSide),
                BookAction::Clear => Ok(L2VecDeltaProbe {
                    kind: L2VecMutationKind::Clear,
                    side: None,
                    len_before: self.bids.len() + self.asks.len(),
                    index: None,
                    shifted_levels: 0,
                    shifted_bytes: 0,
                }),
            };
        }

        Ok(match delta.action {
            BookAction::Add | BookAction::Update | BookAction::Delete => self.probe_side_delta(
                order.side.as_specified(),
                delta.action,
                order.price,
                order.size,
            ),
            BookAction::Clear => L2VecDeltaProbe {
                kind: L2VecMutationKind::Clear,
                side: None,
                len_before: self.bids.len() + self.asks.len(),
                index: None,
                shifted_levels: 0,
                shifted_bytes: 0,
            },
        })
    }

    fn apply_add(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        size: Quantity,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        self.observe_precisions(price.precision, size.precision);

        if size.raw != 0 {
            let levels = self.levels_mut(side);
            match Self::find_level_index(levels, side, price) {
                Ok(index) => levels[index].size_raw = size.raw,
                Err(index) => levels.insert(index, Level::new(price, size)),
            }
        }

        self.increment(sequence, ts_event);
    }

    fn apply_update(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        size: Quantity,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        self.observe_precisions(price.precision, size.precision);

        let levels = self.levels_mut(side);
        match Self::find_level_index(levels, side, price) {
            Ok(index) => {
                if size.raw == 0 {
                    levels.remove(index);
                } else {
                    levels[index].size_raw = size.raw;
                }
            }
            Err(index) => {
                if size.raw != 0 {
                    levels.insert(index, Level::new(price, size));
                }
            }
        }

        self.increment(sequence, ts_event);
    }

    fn delete_level(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        let levels = self.levels_mut(side);
        if let Ok(index) = Self::find_level_index(levels, side, price) {
            levels.remove(index);
        }

        self.increment(sequence, ts_event);
    }

    fn clear(&mut self, sequence: u64, ts_event: UnixNanos) {
        self.bids.clear();
        self.asks.clear();
        self.increment(sequence, ts_event);
    }

    fn best_level(&self, side: OrderSideSpecified) -> Option<(Price, Quantity)> {
        self.levels(side).first().copied().map(|level| {
            (
                level.price(self.price_precision),
                level.size(self.size_precision),
            )
        })
    }

    fn checksum(levels: &[Level], depth: usize) -> (i128, u128) {
        levels
            .iter()
            .take(depth)
            .fold((0_i128, 0_u128), |(price_acc, size_acc), level| {
                (
                    price_acc + level.price_raw as i128,
                    size_acc + level.size_raw as u128,
                )
            })
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

impl L2BookOps for L2VecBook {
    const BOOK_LABEL: &'static str = "l2vec";

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
        self.bids.clear();
        self.asks.clear();
        self.sequence = 0;
        self.ts_last = UnixNanos::default();
        self.update_count = 0;
        self.price_precision = 0;
        self.size_precision = 0;
    }

    fn apply_delta_unchecked(&mut self, delta: &OrderBookDelta) -> Result<(), BookIntegrityError> {
        let order = delta.order;

        if order.side == OrderSide::NoOrderSide {
            match delta.action {
                BookAction::Add => return Err(BookIntegrityError::NoOrderSide),
                BookAction::Update | BookAction::Delete if order.order_id != 0 => {
                    log::debug!(
                        "Skipping {:?} for unknown order_id={}",
                        delta.action,
                        order.order_id
                    );
                    return Ok(());
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
            BookAction::Add => self.apply_add(
                order.side.as_specified(),
                order.price,
                order.size,
                sequence,
                ts_event,
            ),
            BookAction::Update => self.apply_update(
                order.side.as_specified(),
                order.price,
                order.size,
                sequence,
                ts_event,
            ),
            BookAction::Delete => {
                self.delete_level(order.side.as_specified(), order.price, sequence, ts_event);
            }
            BookAction::Clear => self.clear(sequence, ts_event),
        }

        Ok(())
    }

    fn best_bid_price(&self) -> Option<Price> {
        self.best_level(OrderSideSpecified::Buy)
            .map(|(price, _)| price)
    }

    fn best_ask_price(&self) -> Option<Price> {
        self.best_level(OrderSideSpecified::Sell)
            .map(|(price, _)| price)
    }

    fn best_bid_size(&self) -> Option<Quantity> {
        self.best_level(OrderSideSpecified::Buy)
            .map(|(_, size)| size)
    }

    fn best_ask_size(&self) -> Option<Quantity> {
        self.best_level(OrderSideSpecified::Sell)
            .map(|(_, size)| size)
    }

    fn top_n_levels(&self, side: OrderSide, depth: usize) -> Vec<(Price, Quantity)> {
        let levels = match side {
            OrderSide::Buy => &self.bids,
            OrderSide::Sell => &self.asks,
            OrderSide::NoOrderSide => return Vec::new(),
        };

        levels
            .iter()
            .take(depth)
            .map(|level| {
                (
                    level.price(self.price_precision),
                    level.size(self.size_precision),
                )
            })
            .collect()
    }

    fn query_depth_checksum(&self, depth: usize) -> ((i128, u128), (i128, u128)) {
        (
            Self::checksum(&self.bids, depth),
            Self::checksum(&self.asks, depth),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        data::{BookOrder, OrderBookDelta},
        enums::BookType,
        orderbook::OrderBook,
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

    fn assert_side(book: &L2VecBook, side: OrderSide, expected: &[(f64, f64)]) {
        let actual: Vec<(Price, Quantity)> = expected
            .iter()
            .map(|(price, size)| {
                (
                    Price::new(*price, PRICE_PRECISION),
                    Quantity::new(*size, SIZE_PRECISION),
                )
            })
            .collect();
        assert_eq!(book.top_n_levels(side, expected.len()), actual);
    }

    fn assert_parity(baseline: &OrderBook, candidate: &L2VecBook) {
        assert_eq!(baseline.best_bid_price(), candidate.best_bid_price());
        assert_eq!(baseline.best_ask_price(), candidate.best_ask_price());
        assert_eq!(baseline.best_bid_size(), candidate.best_bid_size());
        assert_eq!(baseline.best_ask_size(), candidate.best_ask_size());
        assert_eq!(baseline.sequence, candidate.sequence);
        assert_eq!(baseline.ts_last, candidate.ts_last);
        assert_eq!(baseline.update_count, candidate.update_count);
        assert_eq!(
            baseline.top_n_levels(OrderSide::Buy, 10),
            candidate.top_n_levels(OrderSide::Buy, 10)
        );
        assert_eq!(
            baseline.top_n_levels(OrderSide::Sell, 10),
            candidate.top_n_levels(OrderSide::Sell, 10)
        );
    }

    #[test]
    fn test_l2_vec_book_insert_maintains_side_ordering() {
        let mut book = L2VecBook::new(instrument_id());

        for delta in [
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.8, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                1,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(2.0, SIZE_PRECISION),
                2,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.9, PRICE_PRECISION),
                Quantity::new(3.0, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.4, PRICE_PRECISION),
                Quantity::new(4.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.2, PRICE_PRECISION),
                Quantity::new(5.0, SIZE_PRECISION),
                5,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.3, PRICE_PRECISION),
                Quantity::new(6.0, SIZE_PRECISION),
                6,
            ),
        ] {
            book.apply_delta(&delta).unwrap();
        }

        assert_side(
            &book,
            OrderSide::Buy,
            &[(100.0, 2.0), (99.9, 3.0), (99.8, 1.0)],
        );
        assert_side(
            &book,
            OrderSide::Sell,
            &[(100.2, 5.0), (100.3, 6.0), (100.4, 4.0)],
        );
    }

    #[test]
    fn test_l2_vec_book_update_preserves_ordering_and_upserts_missing_level() {
        let mut book = L2VecBook::new(instrument_id());

        for delta in [
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
                1,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.8, PRICE_PRECISION),
                Quantity::new(2.0, SIZE_PRECISION),
                2,
            ),
            delta(
                BookAction::Update,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(4.5, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Update,
                OrderSide::Buy,
                Price::new(99.9, PRICE_PRECISION),
                Quantity::new(3.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Update,
                OrderSide::Sell,
                Price::new(100.2, PRICE_PRECISION),
                Quantity::new(1.5, SIZE_PRECISION),
                5,
            ),
        ] {
            book.apply_delta(&delta).unwrap();
        }

        assert_side(
            &book,
            OrderSide::Buy,
            &[(100.0, 4.5), (99.9, 3.0), (99.8, 2.0)],
        );
        assert_side(&book, OrderSide::Sell, &[(100.2, 1.5)]);
    }

    #[test]
    fn test_l2_vec_book_delete_removes_head_middle_and_tail_levels() {
        let mut book = L2VecBook::new(instrument_id());

        for delta in [
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(1.0, SIZE_PRECISION),
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
                OrderSide::Buy,
                Price::new(99.8, PRICE_PRECISION),
                Quantity::new(3.0, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.7, PRICE_PRECISION),
                Quantity::new(4.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                5,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Buy,
                Price::new(99.8, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                6,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Buy,
                Price::new(99.7, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                7,
            ),
        ] {
            book.apply_delta(&delta).unwrap();
        }

        assert_side(&book, OrderSide::Buy, &[(99.9, 2.0)]);
    }

    #[test]
    fn test_l2_vec_book_clear_removes_both_sides() {
        let mut book = L2VecBook::new(instrument_id());

        book.apply_delta(&delta(
            BookAction::Add,
            OrderSide::Buy,
            Price::new(100.0, PRICE_PRECISION),
            Quantity::new(1.0, SIZE_PRECISION),
            1,
        ))
        .unwrap();
        book.apply_delta(&delta(
            BookAction::Add,
            OrderSide::Sell,
            Price::new(100.2, PRICE_PRECISION),
            Quantity::new(2.0, SIZE_PRECISION),
            2,
        ))
        .unwrap();
        book.apply_delta(&OrderBookDelta::clear(
            instrument_id(),
            3,
            3.into(),
            3.into(),
        ))
        .unwrap();

        assert!(book.bids.is_empty());
        assert!(book.asks.is_empty());
        assert_eq!(book.best_bid_price(), None);
        assert_eq!(book.best_ask_price(), None);
        assert_eq!(book.sequence, 3);
        assert_eq!(book.ts_last, UnixNanos::from(3_u64));
        assert_eq!(book.update_count, 3);
    }

    #[test]
    fn test_l2_vec_book_matches_baseline_for_basic_sequence() {
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
        let mut candidate = L2VecBook::new(instrument_id());

        for delta in &deltas {
            baseline.apply_delta(delta).unwrap();
            candidate.apply_delta(delta).unwrap();
            assert_parity(&baseline, &candidate);
        }
    }

    #[test]
    fn test_l2_vec_book_update_missing_level_upserts_like_baseline() {
        let delta = delta(
            BookAction::Update,
            OrderSide::Buy,
            Price::new(99.8, PRICE_PRECISION),
            Quantity::new(5.0, SIZE_PRECISION),
            1,
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2VecBook::new(instrument_id());

        baseline.apply_delta(&delta).unwrap();
        candidate.apply_delta(&delta).unwrap();

        assert_parity(&baseline, &candidate);
    }

    #[test]
    fn test_l2_vec_book_delete_missing_level_is_noop_like_baseline() {
        let delta = delta(
            BookAction::Delete,
            OrderSide::Buy,
            Price::new(101.0, PRICE_PRECISION),
            Quantity::new(1.0, SIZE_PRECISION),
            1,
        );

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2VecBook::new(instrument_id());

        baseline.apply_delta(&delta).unwrap();
        candidate.apply_delta(&delta).unwrap();

        assert_parity(&baseline, &candidate);
    }
}
