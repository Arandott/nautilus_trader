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

use std::path::PathBuf;

use nautilus_model::{
    enums::{BookType, OrderSide},
    orderbook::{L2BookOps, L2VecBook, OrderBook},
};
use nautilus_tardis::csv::stream_deltas;

fn sample_csv_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("test_data/csv/deltas_with_snapshot.csv")
}

fn assert_parity(baseline: &OrderBook, candidate: &L2VecBook) {
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
fn test_l2_vec_book_matches_baseline_on_tardis_sample_csv() {
    let stream = stream_deltas(sample_csv_path(), 2, None, None, None, None).unwrap();
    let mut baseline: Option<OrderBook> = None;
    let mut candidate: Option<L2VecBook> = None;

    for chunk in stream {
        let deltas = chunk.unwrap();
        if deltas.is_empty() {
            continue;
        }

        let instrument_id = deltas[0].instrument_id;
        let baseline_ref =
            baseline.get_or_insert_with(|| OrderBook::new(instrument_id, BookType::L2_MBP));
        let candidate_ref = candidate.get_or_insert_with(|| L2VecBook::new(instrument_id));

        for delta in deltas {
            baseline_ref.apply_delta(&delta).unwrap();
            candidate_ref.apply_delta(&delta).unwrap();
            assert_parity(baseline_ref, candidate_ref);
        }
    }

    assert!(baseline.is_some());
    assert!(candidate.is_some());
}
