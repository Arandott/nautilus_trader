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

//! Experimental chunked sparse-grid L2 book.
//!
//! Implementation note:
//! - Each side stores sparse pages keyed by `page_id`, not individual price levels. The mapping is
//!   `page_id = price.raw.div_euclid(PAGE_SIZE)` and
//!   `slot = price.raw.rem_euclid(PAGE_SIZE)`.
//! - Each page owns `PAGE_SIZE` fixed slots and tracks occupancy with a `u64` bitmap so page-local
//!   best-level lookup and traversal are driven by `leading_zeros` / `trailing_zeros` scans.
//! - Each side maintains explicit `best_page` / `best_tick` caches. Delete-best repair first scans
//!   the same page, then falls back to the next populated page on that side.
//! - Empty pages are reclaimed immediately, and page bitmap / slot storage are kept in lock-step.

use std::{
    collections::BTreeMap,
    fmt::Display,
    mem::size_of,
    ops::Bound::{Excluded, Unbounded},
};

use nautilus_core::UnixNanos;
use serde::Serialize;

use crate::{
    data::{OrderBookDelta, OrderBookDeltas},
    enums::{BookAction, OrderSide, OrderSideSpecified},
    identifiers::InstrumentId,
    orderbook::{BookIntegrityError, L2BookOps},
    types::{Price, Quantity, price::PriceRaw},
};

const PAGE_SIZE: usize = 64;

type PriceTick = PriceRaw;
type PageId = PriceTick;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2GridLayoutStats {
    pub page_size: usize,
    pub page_id_size_bytes: usize,
    pub price_raw_size_bytes: usize,
    pub price_size_bytes: usize,
    pub quantity_size_bytes: usize,
    pub grid_level_size_bytes: usize,
    pub option_grid_level_size_bytes: usize,
    pub btree_map_size_bytes: usize,
    pub option_page_id_size_bytes: usize,
    pub option_price_tick_size_bytes: usize,
    pub grid_page_size_bytes: usize,
    pub side_grid_size_bytes: usize,
    pub l2_grid_book_size_bytes: usize,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2GridSideDiagnosticSnapshot {
    pub active_pages: u64,
    pub active_levels: u64,
    pub min_page_id: Option<PriceRaw>,
    pub max_page_id: Option<PriceRaw>,
    pub best_page: Option<PriceRaw>,
    pub best_tick: Option<PriceRaw>,
    pub occupancy_histogram: Vec<u64>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct L2GridDiagnosticSnapshot {
    pub bids: L2GridSideDiagnosticSnapshot,
    pub asks: L2GridSideDiagnosticSnapshot,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct GridLevel {
    size: Quantity,
    price_precision: u8,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct GridPage {
    base_tick: PriceTick,
    levels: [Option<GridLevel>; PAGE_SIZE],
    occupancy_bitmap: u64,
    active_count: u8,
}

impl GridPage {
    fn new(page_id: PageId) -> Self {
        Self {
            base_tick: SideGrid::page_base_tick(page_id),
            levels: [None; PAGE_SIZE],
            occupancy_bitmap: 0,
            active_count: 0,
        }
    }

    fn slot_mask(slot: usize) -> u64 {
        debug_assert!(slot < PAGE_SIZE);
        1_u64 << slot
    }

    fn slot_tick(&self, slot: usize) -> PriceTick {
        self.base_tick + slot as PriceTick
    }

    fn is_empty(&self) -> bool {
        self.occupancy_bitmap == 0
    }

    fn is_occupied(&self, slot: usize) -> bool {
        self.occupancy_bitmap & Self::slot_mask(slot) != 0
    }

    fn upsert(&mut self, slot: usize, price_precision: u8, size: Quantity) {
        if !self.is_occupied(slot) {
            self.occupancy_bitmap |= Self::slot_mask(slot);
            self.active_count += 1;
        }

        self.levels[slot] = Some(GridLevel {
            size,
            price_precision,
        });
        debug_assert!(self.bitmap_matches_slots());
    }

    fn remove(&mut self, slot: usize) -> Option<GridLevel> {
        if !self.is_occupied(slot) {
            return None;
        }

        self.occupancy_bitmap &= !Self::slot_mask(slot);
        debug_assert!(self.active_count > 0);
        self.active_count -= 1;

        let removed = self.levels[slot].take();
        debug_assert!(removed.is_some(), "bitmap and slot storage diverged");
        debug_assert!(self.bitmap_matches_slots());

        removed
    }

    fn best_slot(&self, side: OrderSideSpecified) -> Option<usize> {
        if self.occupancy_bitmap == 0 {
            return None;
        }

        Some(match side {
            OrderSideSpecified::Buy => 63 - self.occupancy_bitmap.leading_zeros() as usize,
            OrderSideSpecified::Sell => self.occupancy_bitmap.trailing_zeros() as usize,
        })
    }

    fn best_tick(&self, side: OrderSideSpecified) -> Option<PriceTick> {
        self.best_slot(side).map(|slot| self.slot_tick(slot))
    }

    fn level_at(&self, slot: usize) -> Option<(Price, Quantity)> {
        self.levels[slot].as_ref().map(|level| {
            (
                Price::from_raw(self.slot_tick(slot), level.price_precision),
                level.size,
            )
        })
    }

    fn visit_levels<F>(&self, side: OrderSideSpecified, remaining: &mut usize, f: &mut F)
    where
        F: FnMut(Price, Quantity),
    {
        let mut bitmap = self.occupancy_bitmap;

        while bitmap != 0 && *remaining > 0 {
            let slot = match side {
                OrderSideSpecified::Buy => 63 - bitmap.leading_zeros() as usize,
                OrderSideSpecified::Sell => bitmap.trailing_zeros() as usize,
            };
            let mask = Self::slot_mask(slot);
            let level = self.levels[slot]
                .as_ref()
                .expect("bitmap and slot storage diverged");
            let price = Price::from_raw(self.slot_tick(slot), level.price_precision);

            f(price, level.size);
            bitmap &= !mask;
            *remaining -= 1;
        }
    }

    fn bitmap_matches_slots(&self) -> bool {
        let mut expected_bitmap = 0_u64;
        let mut expected_count = 0_u8;

        for (slot, level) in self.levels.iter().enumerate() {
            if level.is_some() {
                expected_bitmap |= Self::slot_mask(slot);
                expected_count += 1;
            }
        }

        expected_bitmap == self.occupancy_bitmap && expected_count == self.active_count
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct SideGrid {
    side: OrderSideSpecified,
    pages: BTreeMap<PageId, GridPage>,
    best_page: Option<PageId>,
    best_tick: Option<PriceTick>,
}

impl SideGrid {
    fn new(side: OrderSideSpecified) -> Self {
        Self {
            side,
            pages: BTreeMap::new(),
            best_page: None,
            best_tick: None,
        }
    }

    fn price_to_tick(price: Price) -> PriceTick {
        price.raw
    }

    fn page_id_and_slot(tick: PriceTick) -> (PageId, usize) {
        let page_size = PAGE_SIZE as PriceTick;
        let page_id = tick.div_euclid(page_size);
        let slot = tick.rem_euclid(page_size) as usize;
        (page_id, slot)
    }

    fn page_base_tick(page_id: PageId) -> PriceTick {
        page_id * PAGE_SIZE as PriceTick
    }

    fn is_better_tick(&self, candidate: PriceTick, current_best: PriceTick) -> bool {
        match self.side {
            OrderSideSpecified::Buy => candidate > current_best,
            OrderSideSpecified::Sell => candidate < current_best,
        }
    }

    fn cached_best(&self) -> Option<(PageId, PriceTick)> {
        self.best_page.zip(self.best_tick)
    }

    fn clear_best(&mut self) {
        self.best_page = None;
        self.best_tick = None;
    }

    fn best_page_and_tick_for_pages(&self) -> Option<(PageId, PriceTick)> {
        let (&page_id, page) = match self.side {
            OrderSideSpecified::Buy => self.pages.iter().next_back()?,
            OrderSideSpecified::Sell => self.pages.iter().next()?,
        };

        let tick = page
            .best_tick(self.side)
            .expect("non-empty page missing best tick");
        Some((page_id, tick))
    }

    fn repair_best_after_delete(&mut self, deleted_page: PageId) {
        if let Some(page) = self.pages.get(&deleted_page) {
            if let Some(tick) = page.best_tick(self.side) {
                self.best_page = Some(deleted_page);
                self.best_tick = Some(tick);
                return;
            }
        }

        let next_page = match self.side {
            OrderSideSpecified::Buy => self.pages.range(..deleted_page).next_back(),
            OrderSideSpecified::Sell => {
                self.pages.range((Excluded(deleted_page), Unbounded)).next()
            }
        };

        if let Some((&page_id, page)) = next_page {
            self.best_page = Some(page_id);
            self.best_tick = page.best_tick(self.side);
        } else {
            self.clear_best();
        }
    }

    fn upsert(&mut self, price: Price, size: Quantity) {
        let tick = Self::price_to_tick(price);
        let (page_id, slot) = Self::page_id_and_slot(tick);

        self.pages
            .entry(page_id)
            .or_insert_with(|| GridPage::new(page_id))
            .upsert(slot, price.precision, size);

        match self.best_tick {
            Some(current_best) if !self.is_better_tick(tick, current_best) => {}
            _ => {
                self.best_page = Some(page_id);
                self.best_tick = Some(tick);
            }
        }

        debug_assert_eq!(self.cached_best(), self.best_page_and_tick_for_pages());
    }

    fn delete(&mut self, price: Price) {
        let tick = Self::price_to_tick(price);
        let (page_id, slot) = Self::page_id_and_slot(tick);
        let was_best = self.best_tick == Some(tick);

        let (removed, page_empty) = match self.pages.get_mut(&page_id) {
            Some(page) => {
                let removed = page.remove(slot);
                let page_empty = page.is_empty();
                (removed, page_empty)
            }
            None => return,
        };

        if removed.is_none() {
            return;
        }

        if page_empty {
            self.pages.remove(&page_id);
        }

        if was_best {
            self.repair_best_after_delete(page_id);
        }

        if self.pages.is_empty() {
            self.clear_best();
        }

        debug_assert_eq!(self.cached_best(), self.best_page_and_tick_for_pages());
    }

    fn clear(&mut self) {
        self.pages.clear();
        self.clear_best();
    }

    fn best_level(&self) -> Option<(Price, Quantity)> {
        debug_assert_eq!(self.cached_best(), self.best_page_and_tick_for_pages());

        let (page_id, tick) = self.cached_best()?;
        let (derived_page_id, slot) = Self::page_id_and_slot(tick);
        debug_assert_eq!(page_id, derived_page_id);

        self.pages
            .get(&page_id)
            .and_then(|page| page.level_at(slot))
    }

    fn visit_top_levels<F>(&self, depth: usize, mut f: F)
    where
        F: FnMut(Price, Quantity),
    {
        if depth == 0 {
            return;
        }

        let mut remaining = depth;

        match self.side {
            OrderSideSpecified::Buy => {
                for page in self.pages.values().rev() {
                    page.visit_levels(self.side, &mut remaining, &mut f);
                    if remaining == 0 {
                        break;
                    }
                }
            }
            OrderSideSpecified::Sell => {
                for page in self.pages.values() {
                    page.visit_levels(self.side, &mut remaining, &mut f);
                    if remaining == 0 {
                        break;
                    }
                }
            }
        }
    }

    fn top_n_levels(&self, depth: usize) -> Vec<(Price, Quantity)> {
        let mut levels = Vec::with_capacity(depth);
        self.visit_top_levels(depth, |price, size| levels.push((price, size)));
        levels
    }

    fn depth_checksum(&self, depth: usize) -> (i128, u128) {
        let mut checksum = (0_i128, 0_u128);

        self.visit_top_levels(depth, |price, size| {
            checksum.0 += price.raw as i128;
            checksum.1 += size.raw as u128;
        });

        checksum
    }

    fn diagnostic_snapshot(&self) -> L2GridSideDiagnosticSnapshot {
        let mut occupancy_histogram = vec![0_u64; PAGE_SIZE + 1];
        let mut active_levels = 0_u64;

        for page in self.pages.values() {
            let active_count = usize::from(page.active_count);
            occupancy_histogram[active_count] += 1;
            active_levels += u64::from(page.active_count);
        }

        L2GridSideDiagnosticSnapshot {
            active_pages: self.pages.len() as u64,
            active_levels,
            min_page_id: self.pages.first_key_value().map(|(page_id, _)| *page_id),
            max_page_id: self.pages.last_key_value().map(|(page_id, _)| *page_id),
            best_page: self.best_page,
            best_tick: self.best_tick,
            occupancy_histogram,
        }
    }
}

/// Chunked sparse-grid-backed L2-MBP order book keyed by price ticks.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct L2GridBook {
    /// The instrument ID for the order book.
    pub instrument_id: InstrumentId,
    /// The last event sequence number for the order book.
    pub sequence: u64,
    /// The timestamp of the last event applied to the order book.
    pub ts_last: UnixNanos,
    /// The current count of updates applied to the order book.
    pub update_count: u64,
    bids: SideGrid,
    asks: SideGrid,
}

impl Display for L2GridBook {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}(instrument_id={}, book_type=L2_MBP, update_count={})",
            stringify!(L2GridBook),
            self.instrument_id,
            self.update_count,
        )
    }
}

impl L2GridBook {
    #[must_use]
    pub fn new(instrument_id: InstrumentId) -> Self {
        Self {
            instrument_id,
            sequence: 0,
            ts_last: UnixNanos::default(),
            update_count: 0,
            bids: SideGrid::new(OrderSideSpecified::Buy),
            asks: SideGrid::new(OrderSideSpecified::Sell),
        }
    }

    #[must_use]
    pub fn diagnostic_layout() -> L2GridLayoutStats {
        L2GridLayoutStats {
            page_size: PAGE_SIZE,
            page_id_size_bytes: size_of::<PageId>(),
            price_raw_size_bytes: size_of::<PriceRaw>(),
            price_size_bytes: size_of::<Price>(),
            quantity_size_bytes: size_of::<Quantity>(),
            grid_level_size_bytes: size_of::<GridLevel>(),
            option_grid_level_size_bytes: size_of::<Option<GridLevel>>(),
            btree_map_size_bytes: size_of::<BTreeMap<PageId, GridPage>>(),
            option_page_id_size_bytes: size_of::<Option<PageId>>(),
            option_price_tick_size_bytes: size_of::<Option<PriceTick>>(),
            grid_page_size_bytes: size_of::<GridPage>(),
            side_grid_size_bytes: size_of::<SideGrid>(),
            l2_grid_book_size_bytes: size_of::<L2GridBook>(),
        }
    }

    #[must_use]
    pub fn diagnostic_snapshot(&self) -> L2GridDiagnosticSnapshot {
        L2GridDiagnosticSnapshot {
            bids: self.bids.diagnostic_snapshot(),
            asks: self.asks.diagnostic_snapshot(),
        }
    }

    fn levels(&self, side: OrderSideSpecified) -> &SideGrid {
        match side {
            OrderSideSpecified::Buy => &self.bids,
            OrderSideSpecified::Sell => &self.asks,
        }
    }

    fn levels_mut(&mut self, side: OrderSideSpecified) -> &mut SideGrid {
        match side {
            OrderSideSpecified::Buy => &mut self.bids,
            OrderSideSpecified::Sell => &mut self.asks,
        }
    }

    fn upsert_level(
        &mut self,
        side: OrderSideSpecified,
        price: Price,
        size: Quantity,
        sequence: u64,
        ts_event: UnixNanos,
    ) {
        if size.is_positive() {
            self.levels_mut(side).upsert(price, size);
        } else {
            self.levels_mut(side).delete(price);
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
        self.levels_mut(side).delete(price);
        self.increment(sequence, ts_event);
    }

    fn clear(&mut self, sequence: u64, ts_event: UnixNanos) {
        self.bids.clear();
        self.asks.clear();
        self.increment(sequence, ts_event);
    }

    fn best_level(&self, side: OrderSideSpecified) -> Option<(Price, Quantity)> {
        self.levels(side).best_level()
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

impl L2BookOps for L2GridBook {
    const BOOK_LABEL: &'static str = "l2grid";

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
            BookAction::Add | BookAction::Update => {
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

    fn apply_deltas(&mut self, deltas: &OrderBookDeltas) -> Result<(), BookIntegrityError> {
        if deltas.instrument_id != self.instrument_id {
            return Err(BookIntegrityError::InstrumentMismatch(
                self.instrument_id,
                deltas.instrument_id,
            ));
        }

        self.apply_deltas_unchecked(deltas)
    }

    fn apply_deltas_unchecked(
        &mut self,
        deltas: &OrderBookDeltas,
    ) -> Result<(), BookIntegrityError> {
        for delta in &deltas.deltas {
            self.apply_delta_unchecked(delta)?;
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
        match side {
            OrderSide::Buy => self.bids.top_n_levels(depth),
            OrderSide::Sell => self.asks.top_n_levels(depth),
            OrderSide::NoOrderSide => Vec::new(),
        }
    }

    fn query_depth_checksum(&self, depth: usize) -> ((i128, u128), (i128, u128)) {
        (
            self.bids.depth_checksum(depth),
            self.asks.depth_checksum(depth),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{data::BookOrder, enums::BookType, orderbook::OrderBook};

    const PRICE_PRECISION: u8 = 1;
    const SIZE_PRECISION: u8 = 3;

    fn instrument_id() -> InstrumentId {
        InstrumentId::from("BTCUSDT.BINANCE")
    }

    fn raw_price(raw: PriceRaw) -> Price {
        Price::from_raw(raw, PRICE_PRECISION)
    }

    fn raw_size(raw: u64) -> Quantity {
        Quantity::from_raw(raw, SIZE_PRECISION)
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

    fn assert_parity<B: L2BookOps>(baseline: &OrderBook, candidate: &B) {
        assert_eq!(baseline.best_bid_price(), candidate.best_bid_price());
        assert_eq!(baseline.best_ask_price(), candidate.best_ask_price());
        assert_eq!(baseline.best_bid_size(), candidate.best_bid_size());
        assert_eq!(baseline.best_ask_size(), candidate.best_ask_size());
        assert_eq!(baseline.sequence, candidate.sequence());
        assert_eq!(baseline.ts_last, candidate.ts_last());
        assert_eq!(baseline.update_count, candidate.update_count());
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
    fn test_tick_conversion_uses_canonical_price_raw() {
        let coarse = Price::new(100.0, 1);
        let fine = Price::new(100.00, 2);

        assert_eq!(SideGrid::price_to_tick(coarse), coarse.raw);
        assert_eq!(
            SideGrid::price_to_tick(coarse),
            SideGrid::price_to_tick(fine)
        );
    }

    #[test]
    fn test_page_id_and_slot_use_euclidean_division() {
        assert_eq!(SideGrid::page_id_and_slot(0), (0, 0));
        assert_eq!(SideGrid::page_id_and_slot(63), (0, 63));
        assert_eq!(SideGrid::page_id_and_slot(64), (1, 0));
        assert_eq!(SideGrid::page_id_and_slot(-1), (-1, 63));
        assert_eq!(SideGrid::page_id_and_slot(-64), (-1, 0));
        assert_eq!(SideGrid::page_id_and_slot(-65), (-2, 63));
    }

    #[test]
    fn test_best_pointer_recovers_within_same_page() {
        let mut book = L2GridBook::new(instrument_id());
        let base_tick = 10 * PAGE_SIZE as PriceRaw;

        book.upsert_level(
            OrderSideSpecified::Buy,
            raw_price(base_tick + 3),
            raw_size(1),
            1,
            1.into(),
        );
        book.upsert_level(
            OrderSideSpecified::Buy,
            raw_price(base_tick + 11),
            raw_size(2),
            2,
            2.into(),
        );
        book.upsert_level(
            OrderSideSpecified::Buy,
            raw_price(base_tick + 27),
            raw_size(3),
            3,
            3.into(),
        );

        assert_eq!(book.best_bid_price(), Some(raw_price(base_tick + 27)));

        book.delete_level(
            OrderSideSpecified::Buy,
            raw_price(base_tick + 27),
            4,
            4.into(),
        );

        assert_eq!(book.best_bid_price(), Some(raw_price(base_tick + 11)));
        assert_eq!(book.bids.best_page, Some(10));
        assert_eq!(book.bids.best_tick, Some(base_tick + 11));
    }

    #[test]
    fn test_best_pointer_recovers_across_pages() {
        let mut book = L2GridBook::new(instrument_id());
        let high_page = 20 * PAGE_SIZE as PriceRaw;
        let low_page = 18 * PAGE_SIZE as PriceRaw;

        book.upsert_level(
            OrderSideSpecified::Buy,
            raw_price(low_page + 7),
            raw_size(1),
            1,
            1.into(),
        );
        book.upsert_level(
            OrderSideSpecified::Buy,
            raw_price(high_page + 5),
            raw_size(2),
            2,
            2.into(),
        );

        assert_eq!(book.best_bid_price(), Some(raw_price(high_page + 5)));

        book.delete_level(
            OrderSideSpecified::Buy,
            raw_price(high_page + 5),
            3,
            3.into(),
        );

        assert_eq!(book.best_bid_price(), Some(raw_price(low_page + 7)));
        assert_eq!(book.bids.best_page, Some(18));
        assert_eq!(book.bids.best_tick, Some(low_page + 7));
    }

    #[test]
    fn test_zero_size_upsert_removes_level() {
        let mut book = L2GridBook::new(instrument_id());
        let price = Price::new(100.0, PRICE_PRECISION);

        book.upsert_level(
            OrderSideSpecified::Buy,
            price,
            Quantity::new(2.0, SIZE_PRECISION),
            1,
            1.into(),
        );
        book.upsert_level(
            OrderSideSpecified::Buy,
            price,
            Quantity::new(0.0, SIZE_PRECISION),
            2,
            2.into(),
        );

        assert_eq!(book.best_bid_price(), None);
        assert!(book.top_n_levels(OrderSide::Buy, 1).is_empty());
        assert!(book.bids.pages.is_empty());
    }

    #[test]
    fn test_empty_pages_are_reclaimed() {
        let mut book = L2GridBook::new(instrument_id());
        let far_left = raw_price(-2 * PAGE_SIZE as PriceRaw + 9);
        let far_right = raw_price(4 * PAGE_SIZE as PriceRaw + 1);

        book.upsert_level(OrderSideSpecified::Sell, far_left, raw_size(1), 1, 1.into());
        book.upsert_level(
            OrderSideSpecified::Sell,
            far_right,
            raw_size(2),
            2,
            2.into(),
        );

        assert_eq!(book.asks.pages.len(), 2);

        book.delete_level(OrderSideSpecified::Sell, far_left, 3, 3.into());
        assert_eq!(book.asks.pages.len(), 1);
        assert!(!book.asks.pages.contains_key(&-2));

        book.delete_level(OrderSideSpecified::Sell, far_right, 4, 4.into());
        assert!(book.asks.pages.is_empty());
        assert_eq!(book.best_ask_price(), None);
    }

    #[test]
    fn test_page_bitmap_and_slots_stay_in_sync() {
        let mut page = GridPage::new(3);
        let base_tick = SideGrid::page_base_tick(3);

        page.upsert(1, raw_price(base_tick + 1).precision, raw_size(1));
        page.upsert(5, raw_price(base_tick + 5).precision, raw_size(2));
        page.upsert(63, raw_price(base_tick + 63).precision, raw_size(3));
        assert!(page.bitmap_matches_slots());

        page.remove(5);
        assert!(page.bitmap_matches_slots());
        assert_eq!(
            page.best_tick(OrderSideSpecified::Buy),
            Some(base_tick + 63)
        );
        assert_eq!(
            page.best_tick(OrderSideSpecified::Sell),
            Some(base_tick + 1)
        );
    }

    #[test]
    fn test_level_price_is_derived_from_slot_tick_and_stored_precision() {
        let mut page = GridPage::new(7);
        let base_tick = SideGrid::page_base_tick(7);
        let price = Price::from_raw(base_tick + 9, 2);
        let size = raw_size(9);

        page.upsert(9, price.precision, size);

        assert_eq!(page.level_at(9), Some((price, size)));
    }

    #[test]
    fn test_clear_resets_both_sides() {
        let mut book = L2GridBook::new(instrument_id());

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
            Price::new(100.1, PRICE_PRECISION),
            Quantity::new(1.5, SIZE_PRECISION),
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

        assert_eq!(book.best_bid_price(), None);
        assert_eq!(book.best_ask_price(), None);
        assert!(book.top_n_levels(OrderSide::Buy, 10).is_empty());
        assert!(book.top_n_levels(OrderSide::Sell, 10).is_empty());
        assert!(book.bids.pages.is_empty());
        assert!(book.asks.pages.is_empty());
        assert_eq!(book.sequence(), 3);
        assert_eq!(book.update_count(), 3);
    }

    #[test]
    fn test_l2_grid_book_matches_baseline_for_basic_sequence() {
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
                Price::new(99.0, PRICE_PRECISION),
                Quantity::new(4.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Sell,
                Price::new(100.1, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                5,
            ),
            OrderBookDelta::clear(instrument_id(), 6, 6.into(), 6.into()),
        ];

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2GridBook::new(instrument_id());

        for delta in &deltas {
            baseline.apply_delta(delta).unwrap();
            candidate.apply_delta(delta).unwrap();
            assert_parity(&baseline, &candidate);
        }
    }

    #[test]
    fn test_l2_grid_book_matches_baseline_for_sparse_sequence() {
        let deltas = vec![
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
                Price::new(80.0, PRICE_PRECISION),
                Quantity::new(5.0, SIZE_PRECISION),
                2,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(100.5, PRICE_PRECISION),
                Quantity::new(1.1, SIZE_PRECISION),
                3,
            ),
            delta(
                BookAction::Add,
                OrderSide::Sell,
                Price::new(130.0, PRICE_PRECISION),
                Quantity::new(6.0, SIZE_PRECISION),
                4,
            ),
            delta(
                BookAction::Update,
                OrderSide::Sell,
                Price::new(130.0, PRICE_PRECISION),
                Quantity::new(4.0, SIZE_PRECISION),
                5,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Buy,
                Price::new(100.0, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                6,
            ),
            delta(
                BookAction::Add,
                OrderSide::Buy,
                Price::new(99.5, PRICE_PRECISION),
                Quantity::new(2.0, SIZE_PRECISION),
                7,
            ),
            delta(
                BookAction::Delete,
                OrderSide::Sell,
                Price::new(100.5, PRICE_PRECISION),
                Quantity::new(0.0, SIZE_PRECISION),
                8,
            ),
        ];

        let mut baseline = OrderBook::new(instrument_id(), BookType::L2_MBP);
        let mut candidate = L2GridBook::new(instrument_id());

        for delta in &deltas {
            baseline.apply_delta(delta).unwrap();
            candidate.apply_delta(delta).unwrap();
            assert_parity(&baseline, &candidate);
        }
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
        let mut candidate = L2GridBook::new(instrument_id());

        let baseline_result = baseline.apply_delta(&delta);
        let candidate_result = candidate.apply_delta(&delta);

        assert_eq!(baseline_result, Ok(()));
        assert_eq!(candidate_result, Ok(()));
        assert_parity(&baseline, &candidate);
    }
}
