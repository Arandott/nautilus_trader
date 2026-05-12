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
    hint::black_box,
    time::{Duration, Instant},
};

use criterion::{Criterion, criterion_group, criterion_main};
use nautilus_model::{
    data::{BookOrder, OrderBookDelta},
    enums::{BookAction, OrderSide},
    identifiers::InstrumentId,
    orderbook::{L2BookOps, L2GridBook, L2TreeBook, L2VecBook, OrderBook},
    types::{Price, Quantity},
};

const PRICE_PRECISION: u8 = 1;
const SIZE_PRECISION: u8 = 3;
const LEVELS_PER_SIDE: usize = 64;
const TOP_DEPTH: usize = 10;
const BASE_PRICE: f64 = 100_000.0;
const INSERT_RESET_POOL: usize = 64;

fn instrument_id() -> InstrumentId {
    InstrumentId::from("BTCUSDT.BINANCE")
}

fn bid_price(index: usize) -> Price {
    Price::new(BASE_PRICE - (index as f64 * 0.1), PRICE_PRECISION)
}

fn ask_price(index: usize) -> Price {
    Price::new(BASE_PRICE + 0.1 + (index as f64 * 0.1), PRICE_PRECISION)
}

fn quantity_for(index: usize) -> Quantity {
    Quantity::new(1.0 + (index as f64 * 0.01), SIZE_PRECISION)
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

fn seeded_book<B: L2BookOps>() -> B {
    let mut book = B::new_l2(instrument_id());
    let mut sequence = 1_u64;

    for level_index in 0..LEVELS_PER_SIDE {
        let bid_delta = delta(
            BookAction::Add,
            OrderSide::Buy,
            bid_price(level_index),
            quantity_for(level_index),
            sequence,
        );
        sequence += 1;
        book.apply_delta(&bid_delta)
            .expect("Seeding bid level should succeed");

        let ask_delta = delta(
            BookAction::Add,
            OrderSide::Sell,
            ask_price(level_index),
            quantity_for(level_index),
            sequence,
        );
        sequence += 1;
        book.apply_delta(&ask_delta)
            .expect("Seeding ask level should succeed");
    }

    book
}

fn consume_best_bid_ask<B: L2BookOps>(book: &B) {
    black_box((
        book.best_bid_price().map(|price| price.raw as i128),
        book.best_ask_price().map(|price| price.raw as i128),
        book.best_bid_size().map(|qty| qty.raw as u128),
        book.best_ask_size().map(|qty| qty.raw as u128),
    ));
}

fn consume_top_n<B: L2BookOps>(book: &B, depth: usize) {
    black_box(book.query_depth_checksum(depth));
}

fn bench_update_existing_level_for<B: L2BookOps>(c: &mut Criterion, name: &str) {
    let mut book = seeded_book::<B>();
    let mut toggle = false;
    let delta_a = delta(
        BookAction::Update,
        OrderSide::Buy,
        bid_price(8),
        Quantity::new(3.250, SIZE_PRECISION),
        10_000,
    );
    let delta_b = delta(
        BookAction::Update,
        OrderSide::Buy,
        bid_price(8),
        Quantity::new(3.750, SIZE_PRECISION),
        10_001,
    );

    c.bench_function(name, |b| {
        b.iter(|| {
            let delta = if toggle { &delta_a } else { &delta_b };
            toggle = !toggle;
            book.apply_delta_unchecked(black_box(delta))
                .expect("Existing L2 level update should succeed");
        });
    });
}

fn bench_insert_new_level_for<B: L2BookOps>(c: &mut Criterion, name: &str) {
    c.bench_function(name, |b| {
        b.iter_custom(|iters| {
            let mut book = seeded_book::<B>();
            let mut total = Duration::ZERO;
            let mut inserted_prices = Vec::with_capacity(INSERT_RESET_POOL);
            let mut sequence = 20_000_u64;

            for _ in 0..iters {
                if inserted_prices.len() == INSERT_RESET_POOL {
                    for price in inserted_prices.drain(..) {
                        let delete_delta = delta(
                            BookAction::Delete,
                            OrderSide::Buy,
                            price,
                            Quantity::new(1.0, SIZE_PRECISION),
                            sequence,
                        );
                        sequence += 1;
                        book.apply_delta_unchecked(&delete_delta)
                            .expect("Cleanup delete for insert benchmark should succeed");
                    }
                }

                let next_index = LEVELS_PER_SIDE + 64 + inserted_prices.len();
                let add_delta = delta(
                    BookAction::Add,
                    OrderSide::Buy,
                    bid_price(next_index),
                    Quantity::new(7.5, SIZE_PRECISION),
                    sequence,
                );
                sequence += 1;

                let started = Instant::now();
                book.apply_delta_unchecked(black_box(&add_delta))
                    .expect("Inserting new L2 level should succeed");
                total += started.elapsed();

                inserted_prices.push(add_delta.order.price);
            }

            total
        });
    });
}

fn bench_delete_existing_level_for<B: L2BookOps>(c: &mut Criterion, name: &str) {
    c.bench_function(name, |b| {
        b.iter_custom(|iters| {
            let removable_levels: Vec<(Price, Quantity)> = (16..48)
                .map(|index| (bid_price(index), quantity_for(index)))
                .collect();
            let mut book = seeded_book::<B>();
            let mut total = Duration::ZERO;
            let mut removed_levels = Vec::with_capacity(removable_levels.len());
            let mut next_level_index = 0_usize;
            let mut sequence = 30_000_u64;

            for _ in 0..iters {
                if next_level_index == removable_levels.len() {
                    for (price, size) in removed_levels.drain(..) {
                        let restore_delta =
                            delta(BookAction::Add, OrderSide::Buy, price, size, sequence);
                        sequence += 1;
                        book.apply_delta_unchecked(&restore_delta)
                            .expect("Restore add for delete benchmark should succeed");
                    }
                    next_level_index = 0;
                }

                let (price, _) = removable_levels[next_level_index];
                next_level_index += 1;

                let delete_delta = delta(
                    BookAction::Delete,
                    OrderSide::Buy,
                    price,
                    Quantity::new(1.0, SIZE_PRECISION),
                    sequence,
                );
                sequence += 1;

                let started = Instant::now();
                book.apply_delta_unchecked(black_box(&delete_delta))
                    .expect("Deleting an existing L2 level should succeed");
                total += started.elapsed();

                removed_levels.push((price, quantity_for(16 + removed_levels.len())));
            }

            total
        });
    });
}

fn bench_best_bid_ask_for<B: L2BookOps>(c: &mut Criterion, name: &str) {
    let book = seeded_book::<B>();

    c.bench_function(name, |b| {
        b.iter(|| consume_best_bid_ask(black_box(&book)));
    });
}

fn bench_top_10_query_for<B: L2BookOps>(c: &mut Criterion, name: &str) {
    let book = seeded_book::<B>();

    c.bench_function(name, |b| {
        b.iter(|| consume_top_n(black_box(&book), TOP_DEPTH));
    });
}

fn bench_update_existing_level(c: &mut Criterion) {
    bench_update_existing_level_for::<OrderBook>(c, "l2_baseline_update_existing_level");
    bench_update_existing_level_for::<L2TreeBook>(c, "l2tree_update_existing_level");
    bench_update_existing_level_for::<L2VecBook>(c, "l2vec_update_existing_level");
    bench_update_existing_level_for::<L2GridBook>(c, "l2grid_update_existing_level");
}

fn bench_insert_new_level(c: &mut Criterion) {
    bench_insert_new_level_for::<OrderBook>(c, "l2_baseline_insert_new_level");
    bench_insert_new_level_for::<L2TreeBook>(c, "l2tree_insert_new_level");
    bench_insert_new_level_for::<L2VecBook>(c, "l2vec_insert_new_level");
    bench_insert_new_level_for::<L2GridBook>(c, "l2grid_insert_new_level");
}

fn bench_delete_existing_level(c: &mut Criterion) {
    bench_delete_existing_level_for::<OrderBook>(c, "l2_baseline_delete_existing_level");
    bench_delete_existing_level_for::<L2TreeBook>(c, "l2tree_delete_existing_level");
    bench_delete_existing_level_for::<L2VecBook>(c, "l2vec_delete_existing_level");
    bench_delete_existing_level_for::<L2GridBook>(c, "l2grid_delete_existing_level");
}

fn bench_best_bid_ask(c: &mut Criterion) {
    bench_best_bid_ask_for::<OrderBook>(c, "l2_baseline_best_bid_ask");
    bench_best_bid_ask_for::<L2TreeBook>(c, "l2tree_best_bid_ask");
    bench_best_bid_ask_for::<L2VecBook>(c, "l2vec_best_bid_ask");
    bench_best_bid_ask_for::<L2GridBook>(c, "l2grid_best_bid_ask");
}

fn bench_top_10_query(c: &mut Criterion) {
    bench_top_10_query_for::<OrderBook>(c, "l2_baseline_top_10_query");
    bench_top_10_query_for::<L2TreeBook>(c, "l2tree_top_10_query");
    bench_top_10_query_for::<L2VecBook>(c, "l2vec_top_10_query");
    bench_top_10_query_for::<L2GridBook>(c, "l2grid_top_10_query");
}

criterion_group! {
    name = benches;
    config = Criterion::default()
        .sample_size(30)
        .warm_up_time(Duration::from_secs(1))
        .measurement_time(Duration::from_secs(5));
    targets =
        bench_update_existing_level,
        bench_insert_new_level,
        bench_delete_existing_level,
        bench_best_bid_ask,
        bench_top_10_query
}
criterion_main!(benches);
