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
use clap::{Parser, ValueEnum};
use nautilus_model::{
    data::{BookOrder, OrderBookDelta},
    enums::{BookAction, OrderSide},
    identifiers::InstrumentId,
    orderbook::{
        L2BookOps, L2GridBook, L2TreeBook, L2VecBook, OrderBook,
        l2_grid::{L2GridDiagnosticSnapshot, L2GridSideDiagnosticSnapshot},
    },
    types::{Price, Quantity, fixed::FIXED_PRECISION, price::PriceRaw},
};
use serde::Serialize;

const PRICE_PRECISION: u8 = FIXED_PRECISION;
const SIZE_PRECISION: u8 = 3;
const BID_BEST_RAW: PriceRaw = 1_000_000_000;
const ASK_BEST_RAW: PriceRaw = 2_000_000_000;

#[derive(Clone, Copy, Debug, ValueEnum)]
enum BookKind {
    #[value(name = "baseline")]
    Baseline,
    #[value(name = "l2tree")]
    L2Tree,
    #[value(name = "l2vec")]
    L2Vec,
    #[value(name = "l2grid")]
    L2Grid,
}

#[derive(Clone, Copy, Debug, ValueEnum, Serialize)]
enum PricePattern {
    #[value(name = "dense_contiguous")]
    DenseContiguous,
    #[value(name = "sparse_jump")]
    SparseJump,
}

#[derive(Clone, Copy, Debug)]
enum ScheduledAction {
    Update,
    Delete,
    Insert,
}

#[derive(Parser, Debug)]
#[command(name = "tardis-l2-synthetic-matrix")]
#[command(about = "Run bounded synthetic L2 workloads for the Phase 2/3 grid workload matrix")]
struct Args {
    #[arg(long, value_enum)]
    book: BookKind,
    #[arg(long, value_enum)]
    price_pattern: PricePattern,
    #[arg(long)]
    levels_per_side: usize,
    #[arg(long)]
    tick_step: u64,
    #[arg(long)]
    operations: u64,
    #[arg(long)]
    update_ratio: u8,
    #[arg(long)]
    insert_ratio: u8,
    #[arg(long)]
    delete_ratio: u8,
    #[arg(long)]
    query_depth: usize,
    #[arg(long)]
    query_interval: u64,
    #[arg(long)]
    output: Option<PathBuf>,
}

#[derive(Debug, Serialize)]
struct SyntheticMatrixReport {
    book: &'static str,
    price_pattern: PricePattern,
    levels_per_side: usize,
    tick_step: u64,
    operations: u64,
    seed_operations: u64,
    update_ratio: u8,
    insert_ratio: u8,
    delete_ratio: u8,
    query_depth: usize,
    query_interval: u64,
    elapsed_ns: u128,
    updates_per_sec: f64,
    query_count: u64,
    query_elapsed_ns: u128,
    avg_query_ns: u128,
    max_query_ns: u128,
    book_update_count: u64,
    current_resident_bytes: Option<u64>,
    peak_resident_bytes: Option<u64>,
    commit_id: String,
    timestamp_utc: String,
    final_grid_snapshot: Option<L2GridDiagnosticSnapshot>,
    final_grid_occupancy: Option<FinalGridOccupancySummary>,
}

#[derive(Debug, Serialize)]
struct FinalGridOccupancySummary {
    bids: FinalGridSideOccupancySummary,
    asks: FinalGridSideOccupancySummary,
}

#[derive(Debug, Serialize)]
struct FinalGridSideOccupancySummary {
    active_pages: u64,
    active_levels: u64,
    avg_active_slots_per_populated_page: f64,
    p50_active_slots_per_populated_page: u64,
    p95_active_slots_per_populated_page: u64,
    max_active_slots_per_page: u64,
    fraction_pages_le_4_slots: f64,
    fraction_pages_ge_32_slots: f64,
    occupancy_histogram: Vec<u64>,
}

#[derive(Debug)]
struct SideState {
    side: OrderSide,
    window_start: PriceRaw,
    active_len: usize,
    update_cursor: usize,
    delete_pair_count: u64,
}

impl SideState {
    fn new(side: OrderSide, active_len: usize) -> Self {
        Self {
            side,
            window_start: 0,
            active_len,
            update_cursor: 0,
            delete_pair_count: 0,
        }
    }

    fn update_rank(&mut self) -> PriceRaw {
        let offset = self.update_cursor % self.active_len;
        self.update_cursor = (self.update_cursor + 1) % self.active_len;
        self.window_start + offset as PriceRaw
    }

    fn delete_rank(&mut self) -> PriceRaw {
        let delete_shallow = self.delete_pair_count.is_multiple_of(2);
        let deleted_rank = if delete_shallow {
            let rank = self.window_start;
            self.window_start += 1;
            rank
        } else {
            self.window_start + self.active_len as PriceRaw - 1
        };
        self.active_len -= 1;
        deleted_rank
    }

    fn insert_rank(&mut self) -> PriceRaw {
        let delete_shallow = self.delete_pair_count.is_multiple_of(2);
        let inserted_rank = if delete_shallow {
            self.window_start + self.active_len as PriceRaw
        } else {
            let rank = self.window_start - 1;
            self.window_start -= 1;
            rank
        };
        self.active_len += 1;
        self.delete_pair_count += 1;
        inserted_rank
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    validate_args(&args)?;

    let report = match args.book {
        BookKind::Baseline => run_scenario::<OrderBook, _>(&args, |_| None),
        BookKind::L2Tree => run_scenario::<L2TreeBook, _>(&args, |_| None),
        BookKind::L2Vec => run_scenario::<L2VecBook, _>(&args, |_| None),
        BookKind::L2Grid => {
            run_scenario::<L2GridBook, _>(&args, |book| Some(book.diagnostic_snapshot()))
        }
    }?;

    let rendered = serde_json::to_string_pretty(&report)?;
    if let Some(output) = &args.output {
        write_output(output, &rendered)?;
    }

    println!("{rendered}");
    Ok(())
}

fn validate_args(args: &Args) -> Result<()> {
    if args.levels_per_side == 0 {
        bail!("`--levels-per-side` must be greater than zero");
    }
    if args.tick_step == 0 {
        bail!("`--tick-step` must be greater than zero");
    }
    if args.operations == 0 {
        bail!("`--operations` must be greater than zero");
    }
    if args.query_depth == 0 {
        bail!("`--query-depth` must be greater than zero");
    }
    if args.query_interval == 0 {
        bail!("`--query-interval` must be greater than zero");
    }
    let ratio_sum =
        u16::from(args.update_ratio) + u16::from(args.insert_ratio) + u16::from(args.delete_ratio);
    if ratio_sum != 100 {
        bail!("update/insert/delete ratios must sum to 100, got {ratio_sum}");
    }
    if args.insert_ratio != args.delete_ratio {
        bail!(
            "this runner requires insert and delete ratios to match, got insert={} delete={}",
            args.insert_ratio,
            args.delete_ratio
        );
    }
    if args.operations % 2 != 0 {
        bail!("`--operations` must be even so bid/ask workloads stay balanced");
    }

    let side_cycle_len =
        u64::from(args.update_ratio) + u64::from(args.insert_ratio) + u64::from(args.delete_ratio);
    if (args.operations / 2) % side_cycle_len != 0 {
        bail!(
            "operations/2 must be divisible by per-side cycle length {side_cycle_len}, got {}",
            args.operations / 2
        );
    }

    match args.price_pattern {
        PricePattern::DenseContiguous if args.tick_step >= 64 => {
            bail!(
                "dense_contiguous requires `--tick-step < 64`, got {}",
                args.tick_step
            );
        }
        PricePattern::SparseJump if args.tick_step < 64 => {
            bail!(
                "sparse_jump requires `--tick-step >= 64`, got {}",
                args.tick_step
            );
        }
        PricePattern::DenseContiguous | PricePattern::SparseJump => {}
    }

    Ok(())
}

fn run_scenario<B, F>(args: &Args, capture_snapshot: F) -> Result<SyntheticMatrixReport>
where
    B: L2BookOps,
    F: FnOnce(&B) -> Option<L2GridDiagnosticSnapshot>,
{
    let timestamp_utc = Utc::now().to_rfc3339();
    let commit_id = current_commit_id();
    let seed_operations = (args.levels_per_side as u64) * 2;
    let tick_step = PriceRaw::try_from(args.tick_step).context("tick_step overflowed PriceRaw")?;

    let mut book = B::new_l2(instrument_id());
    let mut sequence = 1_u64;
    seed_book(&mut book, args.levels_per_side, tick_step, &mut sequence);

    let mut bids = SideState::new(OrderSide::Buy, args.levels_per_side);
    let mut asks = SideState::new(OrderSide::Sell, args.levels_per_side);
    let side_cycle_len =
        u64::from(args.update_ratio) + u64::from(args.insert_ratio) + u64::from(args.delete_ratio);

    let started = Instant::now();
    let mut query_count = 0_u64;
    let mut query_elapsed_ns = 0_u128;
    let mut max_query_ns = 0_u128;

    for operation_index in 0..args.operations {
        let (state, side_step) = if operation_index % 2 == 0 {
            (&mut bids, operation_index / 2)
        } else {
            (&mut asks, operation_index / 2)
        };

        let action = scheduled_action(side_step, args.update_ratio, side_cycle_len);
        let logical_rank = match action {
            ScheduledAction::Update => state.update_rank(),
            ScheduledAction::Delete => state.delete_rank(),
            ScheduledAction::Insert => state.insert_rank(),
        };

        let delta = delta(
            match action {
                ScheduledAction::Update => BookAction::Update,
                ScheduledAction::Delete => BookAction::Delete,
                ScheduledAction::Insert => BookAction::Add,
            },
            state.side,
            logical_price(state.side, logical_rank, tick_step),
            quantity_for(sequence),
            sequence,
        );
        sequence += 1;

        book.apply_delta_unchecked(&delta)
            .context("synthetic matrix failed to apply delta")?;

        if (operation_index + 1) % args.query_interval == 0 {
            let query_started = Instant::now();
            run_queries(&book, args.query_depth);
            let elapsed = query_started.elapsed().as_nanos();
            query_elapsed_ns += elapsed;
            max_query_ns = max_query_ns.max(elapsed);
            query_count += 1;
        }
    }

    let elapsed_ns = started.elapsed().as_nanos();
    let avg_query_ns = if query_count == 0 {
        0
    } else {
        query_elapsed_ns / query_count as u128
    };
    let updates_per_sec = args.operations as f64 / (elapsed_ns as f64 / 1_000_000_000.0);
    let final_grid_snapshot = capture_snapshot(&book);
    let final_grid_occupancy = final_grid_snapshot.as_ref().map(summarize_grid_snapshot);

    Ok(SyntheticMatrixReport {
        book: B::BOOK_LABEL,
        price_pattern: args.price_pattern,
        levels_per_side: args.levels_per_side,
        tick_step: args.tick_step,
        operations: args.operations,
        seed_operations,
        update_ratio: args.update_ratio,
        insert_ratio: args.insert_ratio,
        delete_ratio: args.delete_ratio,
        query_depth: args.query_depth,
        query_interval: args.query_interval,
        elapsed_ns,
        updates_per_sec,
        query_count,
        query_elapsed_ns,
        avg_query_ns,
        max_query_ns,
        book_update_count: book.update_count(),
        current_resident_bytes: status_memory_bytes("VmRSS:"),
        peak_resident_bytes: status_memory_bytes("VmHWM:"),
        commit_id,
        timestamp_utc,
        final_grid_snapshot,
        final_grid_occupancy,
    })
}

fn scheduled_action(side_step: u64, update_ratio: u8, side_cycle_len: u64) -> ScheduledAction {
    let phase = side_step % side_cycle_len;
    if phase < u64::from(update_ratio) {
        ScheduledAction::Update
    } else if (phase - u64::from(update_ratio)).is_multiple_of(2) {
        ScheduledAction::Delete
    } else {
        ScheduledAction::Insert
    }
}

fn seed_book<B: L2BookOps>(
    book: &mut B,
    levels_per_side: usize,
    tick_step: PriceRaw,
    sequence: &mut u64,
) {
    for logical_rank in 0..levels_per_side {
        let bid_delta = delta(
            BookAction::Add,
            OrderSide::Buy,
            logical_price(OrderSide::Buy, logical_rank as PriceRaw, tick_step),
            quantity_for(*sequence),
            *sequence,
        );
        *sequence += 1;
        book.apply_delta_unchecked(&bid_delta)
            .expect("synthetic seed bid should succeed");

        let ask_delta = delta(
            BookAction::Add,
            OrderSide::Sell,
            logical_price(OrderSide::Sell, logical_rank as PriceRaw, tick_step),
            quantity_for(*sequence),
            *sequence,
        );
        *sequence += 1;
        book.apply_delta_unchecked(&ask_delta)
            .expect("synthetic seed ask should succeed");
    }
}

fn logical_price(side: OrderSide, logical_rank: PriceRaw, tick_step: PriceRaw) -> Price {
    let raw = match side {
        OrderSide::Buy => BID_BEST_RAW - logical_rank * tick_step,
        OrderSide::Sell => ASK_BEST_RAW + logical_rank * tick_step,
        OrderSide::NoOrderSide => unreachable!("NoOrderSide is not used in synthetic L2 workloads"),
    };
    Price::from_raw(raw, PRICE_PRECISION)
}

fn quantity_for(sequence: u64) -> Quantity {
    let raw = 1_000_u128 + (sequence % 251) as u128;
    Quantity::from_raw(
        raw * 10_u128.pow(u32::from(FIXED_PRECISION - SIZE_PRECISION)),
        SIZE_PRECISION,
    )
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

fn instrument_id() -> InstrumentId {
    InstrumentId::from("BTCUSDT.BINANCE")
}

fn run_queries<B: L2BookOps>(book: &B, depth: usize) {
    let best = (
        book.best_bid_price().map(|price| price.raw as i128),
        book.best_ask_price().map(|price| price.raw as i128),
        book.best_bid_size().map(|qty| qty.raw as u128),
        book.best_ask_size().map(|qty| qty.raw as u128),
    );
    let (bids, asks) = book.query_depth_checksum(depth);
    black_box((best, bids, asks));
}

fn summarize_grid_snapshot(snapshot: &L2GridDiagnosticSnapshot) -> FinalGridOccupancySummary {
    FinalGridOccupancySummary {
        bids: summarize_grid_side(&snapshot.bids),
        asks: summarize_grid_side(&snapshot.asks),
    }
}

fn summarize_grid_side(snapshot: &L2GridSideDiagnosticSnapshot) -> FinalGridSideOccupancySummary {
    let histogram = snapshot.occupancy_histogram.clone();
    let populated_pages: u128 = histogram
        .iter()
        .skip(1)
        .map(|count| u128::from(*count))
        .sum();
    let weighted_active_slots: u128 = histogram
        .iter()
        .enumerate()
        .skip(1)
        .map(|(active_slots, count)| active_slots as u128 * u128::from(*count))
        .sum();

    FinalGridSideOccupancySummary {
        active_pages: snapshot.active_pages,
        active_levels: snapshot.active_levels,
        avg_active_slots_per_populated_page: if populated_pages == 0 {
            0.0
        } else {
            weighted_active_slots as f64 / populated_pages as f64
        },
        p50_active_slots_per_populated_page: histogram_percentile(&histogram, 0.50),
        p95_active_slots_per_populated_page: histogram_percentile(&histogram, 0.95),
        max_active_slots_per_page: histogram
            .iter()
            .enumerate()
            .rev()
            .find(|(_, count)| **count > 0)
            .map(|(active_slots, _)| active_slots as u64)
            .unwrap_or(0),
        fraction_pages_le_4_slots: histogram_fraction(&histogram, 1, 4),
        fraction_pages_ge_32_slots: histogram_fraction_upper(&histogram, 32),
        occupancy_histogram: histogram,
    }
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

fn status_memory_bytes(label: &str) -> Option<u64> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    let line = status.lines().find(|line| line.starts_with(label))?;
    let value_kib = line.split_whitespace().nth(1)?.parse::<u64>().ok()?;
    Some(value_kib * 1024)
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
