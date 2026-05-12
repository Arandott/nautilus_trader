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
    identifiers::InstrumentId,
    orderbook::{L2BookOps, L2GridBook, L2TreeBook, L2VecBook, OrderBook},
};
use nautilus_tardis::csv::stream_deltas;
use serde::Serialize;

const DEFAULT_CHUNK_SIZE: usize = 10_000;

#[derive(Clone, Copy, Debug, ValueEnum)]
enum Mode {
    #[value(name = "parse_only")]
    ParseOnly,
    #[value(name = "replay_only")]
    ReplayOnly,
    #[value(name = "replay_periodic_query")]
    ReplayPeriodicQuery,
}

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

#[derive(Parser, Debug)]
#[command(name = "tardis-l2-baseline")]
#[command(about = "Replay runner for baseline and experimental L2 book implementations")]
struct Args {
    #[arg(long)]
    dataset: PathBuf,
    #[arg(long, value_enum)]
    mode: Mode,
    #[arg(long, value_enum, default_value_t = BookKind::Baseline)]
    book: BookKind,
    #[arg(long, default_value_t = 10)]
    depth: usize,
    #[arg(long)]
    query_interval: Option<u64>,
    #[arg(long)]
    limit: Option<usize>,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long)]
    price_precision: Option<u8>,
    #[arg(long)]
    size_precision: Option<u8>,
}

#[derive(Debug, Serialize)]
struct RunnerMetrics {
    dataset: String,
    book: &'static str,
    mode: &'static str,
    depth: usize,
    chunk_size: usize,
    limit: Option<usize>,
    query_interval: Option<u64>,
    instrument_id: Option<String>,
    total_chunks: usize,
    total_deltas: usize,
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
}

fn main() -> Result<()> {
    let args = Args::parse();
    validate_args(&args)?;

    let metrics = run(&args)?;
    let rendered = serde_json::to_string_pretty(&metrics)?;

    if let Some(output) = &args.output {
        write_output(output, &rendered)?;
    }

    println!("{rendered}");
    Ok(())
}

fn validate_args(args: &Args) -> Result<()> {
    if args.depth == 0 {
        bail!("`--depth` must be greater than zero");
    }

    match args.mode {
        Mode::ReplayPeriodicQuery => {
            let interval = args
                .query_interval
                .context("`--query-interval` is required for replay_periodic_query")?;
            if interval == 0 {
                bail!("`--query-interval` must be greater than zero");
            }
        }
        Mode::ParseOnly | Mode::ReplayOnly => {
            if args.query_interval.is_some() {
                bail!("`--query-interval` is only valid for replay_periodic_query");
            }
        }
    }

    Ok(())
}

fn run(args: &Args) -> Result<RunnerMetrics> {
    let timestamp_utc = Utc::now().to_rfc3339();
    let commit_id = current_commit_id();
    match args.mode {
        Mode::ParseOnly => run_parse_only(args, timestamp_utc, commit_id),
        Mode::ReplayOnly | Mode::ReplayPeriodicQuery => match args.book {
            BookKind::Baseline => run_replay::<OrderBook>(args, timestamp_utc, commit_id),
            BookKind::L2Tree => run_replay::<L2TreeBook>(args, timestamp_utc, commit_id),
            BookKind::L2Vec => run_replay::<L2VecBook>(args, timestamp_utc, commit_id),
            BookKind::L2Grid => run_replay::<L2GridBook>(args, timestamp_utc, commit_id),
        },
    }
}

fn run_parse_only(args: &Args, timestamp_utc: String, commit_id: String) -> Result<RunnerMetrics> {
    let stream = stream_deltas(
        &args.dataset,
        DEFAULT_CHUNK_SIZE,
        args.price_precision,
        args.size_precision,
        None,
        args.limit,
    )?;
    let started = Instant::now();

    let mut total_chunks = 0_usize;
    let mut total_deltas = 0_usize;
    let mut instrument_id: Option<InstrumentId> = None;

    for chunk in stream {
        let deltas = chunk?;
        if deltas.is_empty() {
            continue;
        }

        total_chunks += 1;
        if instrument_id.is_none() {
            instrument_id = Some(deltas[0].instrument_id);
        }
        total_deltas += deltas.len();
    }

    finalize_metrics(
        args,
        book_name(args.book),
        timestamp_utc,
        commit_id,
        instrument_id,
        total_chunks,
        total_deltas,
        started.elapsed().as_nanos(),
        0,
        0,
        0,
        0,
    )
}

fn run_replay<B: L2BookOps>(
    args: &Args,
    timestamp_utc: String,
    commit_id: String,
) -> Result<RunnerMetrics> {
    let stream = stream_deltas(
        &args.dataset,
        DEFAULT_CHUNK_SIZE,
        args.price_precision,
        args.size_precision,
        None,
        args.limit,
    )?;
    let started = Instant::now();

    let mut total_chunks = 0_usize;
    let mut total_deltas = 0_usize;
    let mut instrument_id: Option<InstrumentId> = None;
    let mut book: Option<B> = None;
    let mut query_count = 0_u64;
    let mut query_elapsed_ns = 0_u128;
    let mut max_query_ns = 0_u128;

    for chunk in stream {
        let deltas = chunk?;
        if deltas.is_empty() {
            continue;
        }

        total_chunks += 1;

        if instrument_id.is_none() {
            instrument_id = Some(deltas[0].instrument_id);
        }

        let book_ref = book.get_or_insert_with(|| B::new_l2(deltas[0].instrument_id));

        for delta in deltas {
            book_ref
                .apply_delta_unchecked(&delta)
                .context("Failed to apply replay delta")?;
            total_deltas += 1;

            if matches!(args.mode, Mode::ReplayPeriodicQuery)
                && total_deltas as u64 % args.query_interval.expect("validated") == 0
            {
                let query_started = Instant::now();
                run_queries(book_ref, args.depth);
                let elapsed = query_started.elapsed().as_nanos();
                query_elapsed_ns += elapsed;
                max_query_ns = max_query_ns.max(elapsed);
                query_count += 1;
            }
        }
    }

    finalize_metrics(
        args,
        B::BOOK_LABEL,
        timestamp_utc,
        commit_id,
        instrument_id,
        total_chunks,
        total_deltas,
        started.elapsed().as_nanos(),
        query_count,
        query_elapsed_ns,
        max_query_ns,
        book.map_or(0, |book| book.update_count()),
    )
}

fn finalize_metrics(
    args: &Args,
    book: &'static str,
    timestamp_utc: String,
    commit_id: String,
    instrument_id: Option<InstrumentId>,
    total_chunks: usize,
    total_deltas: usize,
    elapsed_ns: u128,
    query_count: u64,
    query_elapsed_ns: u128,
    max_query_ns: u128,
    book_update_count: u64,
) -> Result<RunnerMetrics> {
    if total_deltas == 0 {
        bail!(
            "No deltas were processed from dataset {}",
            args.dataset.display()
        );
    }

    let updates_per_sec = total_deltas as f64 / (elapsed_ns as f64 / 1_000_000_000.0);
    let avg_query_ns = if query_count == 0 {
        0
    } else {
        query_elapsed_ns / query_count as u128
    };

    Ok(RunnerMetrics {
        dataset: args.dataset.display().to_string(),
        book,
        mode: mode_name(args.mode),
        depth: args.depth,
        chunk_size: DEFAULT_CHUNK_SIZE,
        limit: args.limit,
        query_interval: args.query_interval,
        instrument_id: instrument_id.map(|id| id.to_string()),
        total_chunks,
        total_deltas,
        elapsed_ns,
        updates_per_sec,
        query_count,
        query_elapsed_ns,
        avg_query_ns,
        max_query_ns,
        book_update_count,
        current_resident_bytes: status_memory_bytes("VmRSS:"),
        peak_resident_bytes: status_memory_bytes("VmHWM:"),
        commit_id,
        timestamp_utc,
    })
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

fn mode_name(mode: Mode) -> &'static str {
    match mode {
        Mode::ParseOnly => "parse_only",
        Mode::ReplayOnly => "replay_only",
        Mode::ReplayPeriodicQuery => "replay_periodic_query",
    }
}

fn book_name(book: BookKind) -> &'static str {
    match book {
        BookKind::Baseline => "baseline",
        BookKind::L2Tree => "l2tree",
        BookKind::L2Vec => "l2vec",
        BookKind::L2Grid => "l2grid",
    }
}
