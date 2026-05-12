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
    fs,
    hint::black_box,
    path::{Path, PathBuf},
    process::Command,
    time::Instant,
};

use anyhow::{Context, Result, bail};
use chrono::Utc;
use clap::Parser;
use nautilus_model::{
    data::{BookOrder, OrderBookDelta},
    enums::{BookAction, OrderSide},
    identifiers::InstrumentId,
    orderbook::{
        L2BookOps, L2GridBook, L2TreeBook, L2VecBook, OrderBook,
        l2_grid::{L2GridDiagnosticSnapshot, L2GridLayoutStats, L2GridSideDiagnosticSnapshot},
    },
    types::{Price, Quantity},
};
use nautilus_tardis::csv::stream_deltas;
use serde::Serialize;

const DEFAULT_CHUNK_SIZE: usize = 10_000;
const PRICE_PRECISION: u8 = 1;
const SIZE_PRECISION: u8 = 3;
const BASE_PRICE: f64 = 100_000.0;

#[derive(Parser, Debug)]
#[command(name = "tardis-l2-grid-diagnostics")]
#[command(about = "Capture layout, replay occupancy, and deep-query diagnostics for L2GridBook")]
struct Args {
    #[arg(long)]
    dataset: PathBuf,
    #[arg(long, default_value_t = DEFAULT_CHUNK_SIZE)]
    sample_every: usize,
    #[arg(long)]
    limit: Option<usize>,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long, default_value_t = 1024)]
    query_levels_per_side: usize,
    #[arg(long, value_delimiter = ',', default_value = "10,100,500,1000")]
    query_depths: Vec<usize>,
    #[arg(long, default_value_t = 100_000)]
    query_iterations: u64,
    #[arg(long)]
    price_precision: Option<u8>,
    #[arg(long)]
    size_precision: Option<u8>,
}

#[derive(Debug, Serialize)]
struct DiagnosticReport {
    timestamp_utc: String,
    commit_id: String,
    dataset: String,
    limit: Option<usize>,
    sample_every_deltas: usize,
    layout: L2GridLayoutStats,
    layout_derived: LayoutDerivedStats,
    replay_occupancy: ReplayOccupancyReport,
    query_depth_probe: QueryDepthProbeReport,
}

#[derive(Debug, Serialize)]
struct LayoutDerivedStats {
    page_slot_array_bytes: usize,
    page_metadata_bytes: usize,
    effective_page_cost_per_active_level_bytes: Vec<EffectivePageCost>,
}

#[derive(Debug, Serialize)]
struct EffectivePageCost {
    active_slots: usize,
    bytes_per_active_level: f64,
}

#[derive(Debug, Serialize)]
struct ReplayOccupancyReport {
    total_chunks: usize,
    total_deltas: usize,
    sample_count: usize,
    final_snapshot: L2GridDiagnosticSnapshot,
    peak_snapshot: L2GridDiagnosticSnapshot,
    bids: SideOccupancySummary,
    asks: SideOccupancySummary,
}

#[derive(Debug, Serialize)]
struct SideOccupancySummary {
    avg_active_pages_per_sample: f64,
    p50_active_pages_per_sample: u64,
    p95_active_pages_per_sample: u64,
    max_active_pages: u64,
    avg_active_levels_per_sample: f64,
    p50_active_levels_per_sample: u64,
    p95_active_levels_per_sample: u64,
    max_active_levels: u64,
    avg_page_span_per_sample: f64,
    p50_page_span_per_sample: u64,
    p95_page_span_per_sample: u64,
    avg_populated_page_density_in_span: f64,
    avg_active_slots_per_populated_page: f64,
    p50_active_slots_per_populated_page: u64,
    p95_active_slots_per_populated_page: u64,
    max_active_slots_per_page: u64,
    avg_fill_ratio_per_populated_page: f64,
    fraction_pages_le_4_slots: f64,
    fraction_pages_le_8_slots: f64,
    fraction_pages_ge_32_slots: f64,
    occupancy_histogram: Vec<u64>,
}

#[derive(Debug, Serialize)]
struct QueryDepthProbeReport {
    levels_per_side: usize,
    iterations_per_case: u64,
    results: Vec<BookQueryProbe>,
}

#[derive(Debug, Serialize)]
struct BookQueryProbe {
    book: &'static str,
    best_bid_ask_mean_ns: f64,
    query_depths: Vec<DepthTiming>,
}

#[derive(Debug, Serialize)]
struct DepthTiming {
    depth: usize,
    mean_ns: f64,
}

#[derive(Default)]
struct SideAccumulator {
    active_pages_samples: Vec<u64>,
    active_levels_samples: Vec<u64>,
    page_span_samples: Vec<u64>,
    page_density_samples: Vec<f64>,
    occupancy_histogram: Vec<u64>,
}

impl SideAccumulator {
    fn observe(&mut self, snapshot: &L2GridSideDiagnosticSnapshot) {
        self.active_pages_samples.push(snapshot.active_pages);
        self.active_levels_samples.push(snapshot.active_levels);

        let page_span = snapshot
            .max_page_id
            .zip(snapshot.min_page_id)
            .map(|(max_page_id, min_page_id)| {
                u64::try_from(max_page_id - min_page_id + 1).unwrap_or(u64::MAX)
            })
            .unwrap_or(0);
        self.page_span_samples.push(page_span);

        let density = if page_span == 0 {
            0.0
        } else {
            snapshot.active_pages as f64 / page_span as f64
        };
        self.page_density_samples.push(density);

        if self.occupancy_histogram.is_empty() {
            self.occupancy_histogram = vec![0_u64; snapshot.occupancy_histogram.len()];
        }

        for (dst, src) in self
            .occupancy_histogram
            .iter_mut()
            .zip(snapshot.occupancy_histogram.iter())
        {
            *dst += *src;
        }
    }

    fn summarize(&self) -> SideOccupancySummary {
        let populated_pages: u128 = self
            .occupancy_histogram
            .iter()
            .skip(1)
            .map(|count| u128::from(*count))
            .sum();
        let weighted_active_slots: u128 = self
            .occupancy_histogram
            .iter()
            .enumerate()
            .skip(1)
            .map(|(active_slots, count)| active_slots as u128 * u128::from(*count))
            .sum();

        SideOccupancySummary {
            avg_active_pages_per_sample: average_u64(&self.active_pages_samples),
            p50_active_pages_per_sample: percentile_u64(&self.active_pages_samples, 0.50),
            p95_active_pages_per_sample: percentile_u64(&self.active_pages_samples, 0.95),
            max_active_pages: self.active_pages_samples.iter().copied().max().unwrap_or(0),
            avg_active_levels_per_sample: average_u64(&self.active_levels_samples),
            p50_active_levels_per_sample: percentile_u64(&self.active_levels_samples, 0.50),
            p95_active_levels_per_sample: percentile_u64(&self.active_levels_samples, 0.95),
            max_active_levels: self
                .active_levels_samples
                .iter()
                .copied()
                .max()
                .unwrap_or(0),
            avg_page_span_per_sample: average_u64(&self.page_span_samples),
            p50_page_span_per_sample: percentile_u64(&self.page_span_samples, 0.50),
            p95_page_span_per_sample: percentile_u64(&self.page_span_samples, 0.95),
            avg_populated_page_density_in_span: average_f64(&self.page_density_samples),
            avg_active_slots_per_populated_page: if populated_pages == 0 {
                0.0
            } else {
                weighted_active_slots as f64 / populated_pages as f64
            },
            p50_active_slots_per_populated_page: histogram_percentile(
                &self.occupancy_histogram,
                0.50,
            ),
            p95_active_slots_per_populated_page: histogram_percentile(
                &self.occupancy_histogram,
                0.95,
            ),
            max_active_slots_per_page: self
                .occupancy_histogram
                .iter()
                .enumerate()
                .rev()
                .find(|(_, count)| **count > 0)
                .map(|(active_slots, _)| active_slots as u64)
                .unwrap_or(0),
            avg_fill_ratio_per_populated_page: if populated_pages == 0 {
                0.0
            } else {
                weighted_active_slots as f64 / (populated_pages as f64 * 64.0)
            },
            fraction_pages_le_4_slots: histogram_fraction(&self.occupancy_histogram, 1, 4),
            fraction_pages_le_8_slots: histogram_fraction(&self.occupancy_histogram, 1, 8),
            fraction_pages_ge_32_slots: histogram_fraction_upper(&self.occupancy_histogram, 32),
            occupancy_histogram: self.occupancy_histogram.clone(),
        }
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    validate_args(&args)?;

    let report = run(&args)?;
    let rendered = serde_json::to_string_pretty(&report)?;

    if let Some(output) = &args.output {
        write_output(output, &rendered)?;
    }

    println!("{rendered}");
    Ok(())
}

fn validate_args(args: &Args) -> Result<()> {
    if args.sample_every == 0 {
        bail!("`--sample-every` must be greater than zero");
    }
    if args.query_levels_per_side == 0 {
        bail!("`--query-levels-per-side` must be greater than zero");
    }
    if args.query_iterations == 0 {
        bail!("`--query-iterations` must be greater than zero");
    }
    if args.query_depths.is_empty() || args.query_depths.iter().any(|depth| *depth == 0) {
        bail!("`--query-depths` must contain at least one positive depth");
    }

    Ok(())
}

fn run(args: &Args) -> Result<DiagnosticReport> {
    let layout = L2GridBook::diagnostic_layout();
    let timestamp_utc = Utc::now().to_rfc3339();
    let commit_id = current_commit_id();

    Ok(DiagnosticReport {
        timestamp_utc,
        commit_id,
        dataset: args.dataset.display().to_string(),
        limit: args.limit,
        sample_every_deltas: args.sample_every,
        layout_derived: derive_layout_stats(&layout),
        replay_occupancy: capture_replay_occupancy(args)?,
        query_depth_probe: measure_query_depth_probe(args),
        layout,
    })
}

fn derive_layout_stats(layout: &L2GridLayoutStats) -> LayoutDerivedStats {
    let page_slot_array_bytes = layout.option_grid_level_size_bytes * layout.page_size;
    let page_metadata_bytes = layout
        .grid_page_size_bytes
        .saturating_sub(page_slot_array_bytes);
    let effective_page_cost_per_active_level_bytes = [1_usize, 2, 4, 8, 16, 32, 48, 64]
        .into_iter()
        .map(|active_slots| EffectivePageCost {
            active_slots,
            bytes_per_active_level: layout.grid_page_size_bytes as f64 / active_slots as f64,
        })
        .collect();

    LayoutDerivedStats {
        page_slot_array_bytes,
        page_metadata_bytes,
        effective_page_cost_per_active_level_bytes,
    }
}

fn capture_replay_occupancy(args: &Args) -> Result<ReplayOccupancyReport> {
    let stream = stream_deltas(
        &args.dataset,
        DEFAULT_CHUNK_SIZE,
        args.price_precision,
        args.size_precision,
        None,
        args.limit,
    )?;

    let mut total_chunks = 0_usize;
    let mut total_deltas = 0_usize;
    let mut book: Option<L2GridBook> = None;
    let mut bid_accumulator = SideAccumulator::default();
    let mut ask_accumulator = SideAccumulator::default();
    let mut peak_snapshot: Option<L2GridDiagnosticSnapshot> = None;
    let mut peak_total_active_levels = 0_u64;
    let mut next_sample_at = args.sample_every;

    for chunk in stream {
        let deltas = chunk?;
        if deltas.is_empty() {
            continue;
        }

        total_chunks += 1;

        let book_ref = book.get_or_insert_with(|| L2GridBook::new(deltas[0].instrument_id));

        for delta in deltas {
            book_ref
                .apply_delta_unchecked(&delta)
                .context("Failed to apply replay delta in diagnostics")?;
            total_deltas += 1;

            while total_deltas >= next_sample_at {
                let snapshot = book_ref.diagnostic_snapshot();
                observe_snapshot(
                    &snapshot,
                    &mut bid_accumulator,
                    &mut ask_accumulator,
                    &mut peak_snapshot,
                    &mut peak_total_active_levels,
                );
                next_sample_at += args.sample_every;
            }
        }
    }

    if total_deltas == 0 {
        bail!(
            "No deltas were processed from dataset {}",
            args.dataset.display()
        );
    }

    let final_snapshot = book
        .as_ref()
        .map(L2GridBook::diagnostic_snapshot)
        .expect("book exists when total_deltas > 0");

    if total_deltas % args.sample_every != 0 {
        observe_snapshot(
            &final_snapshot,
            &mut bid_accumulator,
            &mut ask_accumulator,
            &mut peak_snapshot,
            &mut peak_total_active_levels,
        );
    }

    Ok(ReplayOccupancyReport {
        total_chunks,
        total_deltas,
        sample_count: bid_accumulator.active_pages_samples.len(),
        final_snapshot,
        peak_snapshot: peak_snapshot.unwrap_or_else(|| L2GridDiagnosticSnapshot {
            bids: L2GridSideDiagnosticSnapshot {
                active_pages: 0,
                active_levels: 0,
                min_page_id: None,
                max_page_id: None,
                best_page: None,
                best_tick: None,
                occupancy_histogram: vec![0; 65],
            },
            asks: L2GridSideDiagnosticSnapshot {
                active_pages: 0,
                active_levels: 0,
                min_page_id: None,
                max_page_id: None,
                best_page: None,
                best_tick: None,
                occupancy_histogram: vec![0; 65],
            },
        }),
        bids: bid_accumulator.summarize(),
        asks: ask_accumulator.summarize(),
    })
}

fn observe_snapshot(
    snapshot: &L2GridDiagnosticSnapshot,
    bid_accumulator: &mut SideAccumulator,
    ask_accumulator: &mut SideAccumulator,
    peak_snapshot: &mut Option<L2GridDiagnosticSnapshot>,
    peak_total_active_levels: &mut u64,
) {
    bid_accumulator.observe(&snapshot.bids);
    ask_accumulator.observe(&snapshot.asks);

    let total_active_levels = snapshot.bids.active_levels + snapshot.asks.active_levels;
    if total_active_levels >= *peak_total_active_levels {
        *peak_total_active_levels = total_active_levels;
        *peak_snapshot = Some(snapshot.clone());
    }
}

fn measure_query_depth_probe(args: &Args) -> QueryDepthProbeReport {
    QueryDepthProbeReport {
        levels_per_side: args.query_levels_per_side,
        iterations_per_case: args.query_iterations,
        results: vec![
            measure_book_query_probe::<OrderBook>("baseline", args),
            measure_book_query_probe::<L2TreeBook>("l2tree", args),
            measure_book_query_probe::<L2VecBook>("l2vec", args),
            measure_book_query_probe::<L2GridBook>("l2grid", args),
        ],
    }
}

fn measure_book_query_probe<B: L2BookOps>(book_name: &'static str, args: &Args) -> BookQueryProbe {
    let book = seeded_book::<B>(args.query_levels_per_side);

    BookQueryProbe {
        book: book_name,
        best_bid_ask_mean_ns: measure_best_bid_ask_ns(&book, args.query_iterations),
        query_depths: args
            .query_depths
            .iter()
            .copied()
            .map(|depth| DepthTiming {
                depth,
                mean_ns: measure_query_depth_ns(&book, depth, args.query_iterations),
            })
            .collect(),
    }
}

fn measure_best_bid_ask_ns<B: L2BookOps>(book: &B, iterations: u64) -> f64 {
    let started = Instant::now();

    for _ in 0..iterations {
        black_box((
            black_box(book)
                .best_bid_price()
                .map(|price| price.raw as i128),
            black_box(book)
                .best_ask_price()
                .map(|price| price.raw as i128),
            black_box(book).best_bid_size().map(|qty| qty.raw as u128),
            black_box(book).best_ask_size().map(|qty| qty.raw as u128),
        ));
    }

    started.elapsed().as_nanos() as f64 / iterations as f64
}

fn measure_query_depth_ns<B: L2BookOps>(book: &B, depth: usize, iterations: u64) -> f64 {
    let started = Instant::now();

    for _ in 0..iterations {
        black_box(black_box(book).query_depth_checksum(depth));
    }

    started.elapsed().as_nanos() as f64 / iterations as f64
}

fn seeded_book<B: L2BookOps>(levels_per_side: usize) -> B {
    let mut book = B::new_l2(instrument_id());
    let mut sequence = 1_u64;

    for level_index in 0..levels_per_side {
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

fn average_u64(values: &[u64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().map(|value| u128::from(*value)).sum::<u128>() as f64 / values.len() as f64
    }
}

fn average_f64(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn percentile_u64(values: &[u64], percentile: f64) -> u64 {
    if values.is_empty() {
        return 0;
    }

    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    let index = ((sorted.len() - 1) as f64 * percentile).round() as usize;
    sorted[index]
}

fn histogram_percentile(histogram: &[u64], percentile: f64) -> u64 {
    let total: u128 = histogram
        .iter()
        .skip(1)
        .map(|count| u128::from(*count))
        .sum();
    if total == 0 {
        return 0;
    }

    let target = (total as f64 * percentile).ceil() as u128;
    let mut cumulative = 0_u128;

    for (active_slots, count) in histogram.iter().enumerate().skip(1) {
        cumulative += u128::from(*count);
        if cumulative >= target {
            return active_slots as u64;
        }
    }

    0
}

fn histogram_fraction(histogram: &[u64], start: usize, end: usize) -> f64 {
    let total: u128 = histogram
        .iter()
        .skip(1)
        .map(|count| u128::from(*count))
        .sum();
    if total == 0 {
        return 0.0;
    }

    let clamped_end = end.min(histogram.len().saturating_sub(1));
    let hits: u128 = histogram[start..=clamped_end]
        .iter()
        .map(|count| u128::from(*count))
        .sum();
    hits as f64 / total as f64
}

fn histogram_fraction_upper(histogram: &[u64], start: usize) -> f64 {
    let total: u128 = histogram
        .iter()
        .skip(1)
        .map(|count| u128::from(*count))
        .sum();
    if total == 0 {
        return 0.0;
    }

    let clamped_start = start.min(histogram.len().saturating_sub(1));
    let hits: u128 = histogram[clamped_start..]
        .iter()
        .map(|count| u128::from(*count))
        .sum();
    hits as f64 / total as f64
}

fn write_output(path: &Path, rendered: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, rendered)?;
    Ok(())
}

fn current_commit_id() -> String {
    Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|output| output.trim().to_string())
        .filter(|output| !output.is_empty())
        .unwrap_or_else(|| "unknown".to_string())
}
