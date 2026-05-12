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

use std::{
    cell::{Ref, RefCell},
    num::NonZeroUsize,
    rc::Rc,
};

use nautilus_common::{
    cache::Cache,
    msgbus::{self, Handler, MStr, Topic},
    timer::TimeEvent,
};
use nautilus_model::{
    data::{OrderBookDeltas, OrderBookDepth10},
    enums::{BookType, OrderSide},
    identifiers::{InstrumentId, Venue},
    instruments::Instrument,
    orderbook::{L2BookBackendKind, L2BookOps, OrderBook},
};
use ustr::Ustr;

/// Contains information for creating snapshots of specific order books.
#[derive(Clone, Debug)]
pub struct BookSnapshotInfo {
    pub instrument_id: InstrumentId,
    pub venue: Venue,
    pub is_composite: bool,
    pub root: Ustr,
    pub topic: MStr<Topic>,
    pub interval_ms: NonZeroUsize,
}

/// Handles order book updates and delta processing for a specific instrument.
///
/// The `BookUpdater` processes incoming order book deltas and maintains
/// the current state of an order book. It can handle both incremental
/// updates and full snapshots for the instrument it's assigned to.
#[derive(Debug)]
pub struct BookUpdater {
    pub id: Ustr,
    pub instrument_id: InstrumentId,
    pub cache: Rc<RefCell<Cache>>,
    shadow_book: Option<RefCell<OrderBook>>,
}

impl BookUpdater {
    /// Creates a new [`BookUpdater`] instance.
    pub fn new(
        instrument_id: &InstrumentId,
        book_type: BookType,
        cache: Rc<RefCell<Cache>>,
        shadow_l2_backend: Option<L2BookBackendKind>,
    ) -> Self {
        let shadow_book = shadow_l2_backend
            .filter(|backend| {
                book_type == BookType::L2_MBP && *backend != L2BookBackendKind::Generic
            })
            .map(|backend| {
                RefCell::new(OrderBook::new_with_l2_backend(
                    *instrument_id,
                    book_type,
                    backend,
                ))
            });

        Self {
            id: Ustr::from(&format!("{}-{}", stringify!(BookUpdater), instrument_id)),
            instrument_id: *instrument_id,
            cache,
            shadow_book,
        }
    }

    fn shadow_apply_deltas(&self, primary: &OrderBook, deltas: &OrderBookDeltas) {
        let Some(shadow_book) = &self.shadow_book else {
            return;
        };

        let mut shadow = shadow_book.borrow_mut();
        if let Err(e) = shadow.apply_deltas(deltas) {
            log::error!(
                "Failed to apply deltas to shadow order book (instrument_id={}): {e}",
                self.instrument_id
            );
            return;
        }

        self.compare_shadow(primary, &shadow, "deltas");
    }

    fn shadow_apply_depth(&self, primary: &OrderBook, depth: &OrderBookDepth10) {
        let Some(shadow_book) = &self.shadow_book else {
            return;
        };

        let mut shadow = shadow_book.borrow_mut();
        if let Err(e) = shadow.apply_depth(depth) {
            log::error!(
                "Failed to apply depth to shadow order book (instrument_id={}): {e}",
                self.instrument_id
            );
            return;
        }

        self.compare_shadow(primary, &shadow, "depth10");
    }

    fn compare_shadow(&self, primary: &OrderBook, shadow: &OrderBook, context: &str) {
        let primary_top10_bids = primary.top_n_levels(OrderSide::Buy, 10);
        let shadow_top10_bids = shadow.top_n_levels(OrderSide::Buy, 10);
        let primary_top10_asks = primary.top_n_levels(OrderSide::Sell, 10);
        let shadow_top10_asks = shadow.top_n_levels(OrderSide::Sell, 10);

        if primary.sequence != shadow.sequence
            || primary.ts_last != shadow.ts_last
            || primary.update_count != shadow.update_count
            || primary.best_bid_price() != shadow.best_bid_price()
            || primary.best_ask_price() != shadow.best_ask_price()
            || primary.best_bid_size() != shadow.best_bid_size()
            || primary.best_ask_size() != shadow.best_ask_size()
            || primary_top10_bids != shadow_top10_bids
            || primary_top10_asks != shadow_top10_asks
        {
            log::error!(
                "L2 shadow divergence after {context} (instrument_id={}, primary_backend={}, shadow_backend={}, primary_sequence={}, shadow_sequence={}, primary_ts_last={}, shadow_ts_last={}, primary_update_count={}, shadow_update_count={}, primary_best_bid={:?}/{:?}, shadow_best_bid={:?}/{:?}, primary_best_ask={:?}/{:?}, shadow_best_ask={:?}/{:?}, primary_bids={:?}, shadow_bids={:?}, primary_asks={:?}, shadow_asks={:?})",
                self.instrument_id,
                primary.l2_backend().as_str(),
                shadow.l2_backend().as_str(),
                primary.sequence,
                shadow.sequence,
                primary.ts_last,
                shadow.ts_last,
                primary.update_count,
                shadow.update_count,
                primary.best_bid_price(),
                primary.best_bid_size(),
                shadow.best_bid_price(),
                shadow.best_bid_size(),
                primary.best_ask_price(),
                primary.best_ask_size(),
                shadow.best_ask_price(),
                shadow.best_ask_size(),
                primary_top10_bids,
                shadow_top10_bids,
                primary_top10_asks,
                shadow_top10_asks,
            );
        }
    }
}

impl Handler<OrderBookDeltas> for BookUpdater {
    fn id(&self) -> Ustr {
        self.id
    }

    fn handle(&self, deltas: &OrderBookDeltas) {
        if let Some(book) = self
            .cache
            .borrow_mut()
            .order_book_mut(&deltas.instrument_id)
        {
            if let Err(e) = book.apply_deltas(deltas) {
                log::error!("Failed to apply deltas: {e}");
                return;
            }
            self.shadow_apply_deltas(book, deltas);
        }
    }
}

impl Handler<OrderBookDepth10> for BookUpdater {
    fn id(&self) -> Ustr {
        self.id
    }

    fn handle(&self, depth: &OrderBookDepth10) {
        if let Some(book) = self.cache.borrow_mut().order_book_mut(&depth.instrument_id) {
            if let Err(e) = book.apply_depth(depth) {
                log::error!("Failed to apply depth: {e}");
                return;
            }
            self.shadow_apply_depth(book, depth);
        }
    }
}

/// Creates periodic snapshots of order books at configured intervals.
///
/// The `BookSnapshotter` generates order book snapshots on timer events,
/// publishing them as market data. This is useful for providing periodic
/// full order book state updates in addition to incremental delta updates.
#[derive(Debug)]
pub struct BookSnapshotter {
    pub id: Ustr,
    pub timer_name: Ustr,
    pub snap_info: BookSnapshotInfo,
    pub cache: Rc<RefCell<Cache>>,
}

impl BookSnapshotter {
    /// Creates a new [`BookSnapshotter`] instance.
    pub fn new(snap_info: BookSnapshotInfo, cache: Rc<RefCell<Cache>>) -> Self {
        let id_str = format!(
            "{}-{}",
            stringify!(BookSnapshotter),
            snap_info.instrument_id
        );
        let timer_name = format!(
            "OrderBook|{}|{}",
            snap_info.instrument_id, snap_info.interval_ms
        );

        Self {
            id: Ustr::from(&id_str),
            timer_name: Ustr::from(&timer_name),
            snap_info,
            cache,
        }
    }

    pub fn snapshot(&self, _event: TimeEvent) {
        log::debug!(
            "BookSnapshotter.snapshot called for {}",
            self.snap_info.instrument_id
        );
        let cache = self.cache.borrow();

        if self.snap_info.is_composite {
            let topic = self.snap_info.topic;
            let underlying = self.snap_info.root;
            for instrument in cache.instruments(&self.snap_info.venue, Some(&underlying)) {
                self.publish_order_book(&instrument.id(), topic, &cache);
            }
        } else {
            self.publish_order_book(&self.snap_info.instrument_id, self.snap_info.topic, &cache);
        }
    }

    fn publish_order_book(
        &self,
        instrument_id: &InstrumentId,
        topic: MStr<Topic>,
        cache: &Ref<Cache>,
    ) {
        let book = cache
            .order_book(instrument_id)
            .unwrap_or_else(|| panic!("OrderBook for {instrument_id} was not in cache"));

        if book.update_count == 0 {
            log::debug!("OrderBook not yet updated for snapshot: {instrument_id}");
            return;
        }
        log::debug!(
            "Publishing OrderBook snapshot for {instrument_id} (update_count={})",
            book.update_count
        );

        msgbus::publish_book(topic, book);
    }
}
