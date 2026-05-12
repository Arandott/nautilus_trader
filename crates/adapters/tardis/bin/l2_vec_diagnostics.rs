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

use std::{collections::BTreeMap, fs, path::PathBuf, process::Command};

use anyhow::{Context, Result};
use chrono::Utc;
use clap::Parser;
use nautilus_model::orderbook::{
    L2BookOps, L2VecBook,
    l2_vec::{L2VecDeltaProbe, L2VecDiagnosticSnapshot, L2VecLayoutStats, L2VecMutationKind},
};
use nautilus_tardis::csv::stream_deltas;
use serde::Serialize;

const DEFAULT_CHUNK_SIZE: usize = 10_000;
const SHIFT_BUCKET_LABELS: [&str; 7] = ["0", "1-4", "5-16", "17-64", "65-256", "257-1024", ">1024"];

#[derive(Parser, Debug)]
#[command(name = "tardis-l2-vec-diagnostics")]
#[command(about = "Capture replay shift economics and capacity snapshots for L2VecBook")]
struct Args {
    #[arg(long)]
    dataset: PathBuf,
    #[arg(long, default_value_t = DEFAULT_CHUNK_SIZE)]
    sample_every: usize,
    #[arg(long)]
    limit: Option<usize>,
    #[arg(long)]
    output: Option<PathBuf>,
}

#[derive(Debug, Serialize)]
struct DiagnosticReport {
    timestamp_utc: String,
    commit_id: String,
    dataset: String,
    limit: Option<usize>,
    sample_every_deltas: usize,
    layout: L2VecLayoutStats,
    replay_shift: ReplayShiftReport,
}

#[derive(Debug, Serialize)]
struct ReplayShiftReport {
    total_deltas: usize,
    total_chunks: usize,
    sample_count: usize,
    final_snapshot: L2VecDiagnosticSnapshot,
    peak_snapshot: L2VecDiagnosticSnapshot,
    operations: OperationSummary,
    bids: SideSummary,
    asks: SideSummary,
}

#[derive(Debug, Serialize)]
struct OperationSummary {
    counts_by_kind: BTreeMap<String, u64>,
    total_shift_events: u64,
    total_shifted_levels: u64,
    total_shifted_bytes: u64,
    avg_shifted_levels_per_shift_event: f64,
    avg_shifted_bytes_per_shift_event: f64,
    avg_shifted_bytes_per_delta: f64,
    max_shifted_levels: u64,
    max_shifted_bytes: u64,
    shift_histogram: Vec<HistogramBucket>,
    insert_positions: PositionCounts,
    remove_positions: PositionCounts,
}

#[derive(Debug, Serialize)]
struct HistogramBucket {
    label: &'static str,
    count: u64,
}

#[derive(Debug, Default, Serialize)]
struct PositionCounts {
    head: u64,
    middle: u64,
    tail: u64,
}

#[derive(Debug, Serialize)]
struct SideSummary {
    avg_active_levels_per_sample: f64,
    p50_active_levels_per_sample: u64,
    p95_active_levels_per_sample: u64,
    max_active_levels: u64,
    avg_reserved_levels_per_sample: f64,
    max_reserved_levels: u64,
    avg_spare_capacity_per_sample: f64,
    max_spare_capacity: u64,
    avg_utilization_per_sample: f64,
}

#[derive(Default)]
struct OperationAccumulator {
    counts_by_kind: BTreeMap<String, u64>,
    total_shift_events: u64,
    total_shifted_levels: u64,
    total_shifted_bytes: u64,
    max_shifted_levels: u64,
    max_shifted_bytes: u64,
    shift_histogram: [u64; SHIFT_BUCKET_LABELS.len()],
    insert_positions: PositionCounts,
    remove_positions: PositionCounts,
}

impl OperationAccumulator {
    fn observe(&mut self, probe: &L2VecDeltaProbe) {
        let key = format!("{:?}", probe.kind);
        *self.counts_by_kind.entry(key).or_insert(0) += 1;

        if probe.shifted_levels > 0 {
            self.total_shift_events += 1;
            self.total_shifted_levels += probe.shifted_levels as u64;
            self.total_shifted_bytes += probe.shifted_bytes as u64;
            self.max_shifted_levels = self.max_shifted_levels.max(probe.shifted_levels as u64);
            self.max_shifted_bytes = self.max_shifted_bytes.max(probe.shifted_bytes as u64);
            self.shift_histogram[shift_bucket_index(probe.shifted_levels)] += 1;
        } else {
            self.shift_histogram[0] += 1;
        }

        match probe.kind {
            L2VecMutationKind::AddInsertNew | L2VecMutationKind::UpdateMissingInsert => {
                classify_position(
                    &mut self.insert_positions,
                    probe.index,
                    probe.len_before,
                    true,
                );
            }
            L2VecMutationKind::UpdateExistingRemove | L2VecMutationKind::DeleteExisting => {
                classify_position(
                    &mut self.remove_positions,
                    probe.index,
                    probe.len_before,
                    false,
                );
            }
            _ => {}
        }
    }

    fn summarize(&self, total_deltas: usize) -> OperationSummary {
        let total_shift_events = self.total_shift_events.max(1);

        OperationSummary {
            counts_by_kind: self.counts_by_kind.clone(),
            total_shift_events: self.total_shift_events,
            total_shifted_levels: self.total_shifted_levels,
            total_shifted_bytes: self.total_shifted_bytes,
            avg_shifted_levels_per_shift_event: self.total_shifted_levels as f64
                / total_shift_events as f64,
            avg_shifted_bytes_per_shift_event: self.total_shifted_bytes as f64
                / total_shift_events as f64,
            avg_shifted_bytes_per_delta: if total_deltas == 0 {
                0.0
            } else {
                self.total_shifted_bytes as f64 / total_deltas as f64
            },
            max_shifted_levels: self.max_shifted_levels,
            max_shifted_bytes: self.max_shifted_bytes,
            shift_histogram: SHIFT_BUCKET_LABELS
                .iter()
                .zip(self.shift_histogram.iter())
                .map(|(label, count)| HistogramBucket {
                    label,
                    count: *count,
                })
                .collect(),
            insert_positions: PositionCounts {
                head: self.insert_positions.head,
                middle: self.insert_positions.middle,
                tail: self.insert_positions.tail,
            },
            remove_positions: PositionCounts {
                head: self.remove_positions.head,
                middle: self.remove_positions.middle,
                tail: self.remove_positions.tail,
            },
        }
    }
}

#[derive(Default)]
struct SideAccumulator {
    active_levels_samples: Vec<u64>,
    reserved_levels_samples: Vec<u64>,
    spare_capacity_samples: Vec<u64>,
    utilization_samples: Vec<f64>,
}

impl SideAccumulator {
    fn observe(&mut self, active_levels: u64, reserved_levels: u64, spare_capacity: u64) {
        self.active_levels_samples.push(active_levels);
        self.reserved_levels_samples.push(reserved_levels);
        self.spare_capacity_samples.push(spare_capacity);
        self.utilization_samples.push(if reserved_levels == 0 {
            0.0
        } else {
            active_levels as f64 / reserved_levels as f64
        });
    }

    fn summarize(&self) -> SideSummary {
        SideSummary {
            avg_active_levels_per_sample: average_u64(&self.active_levels_samples),
            p50_active_levels_per_sample: percentile_u64(&self.active_levels_samples, 0.50),
            p95_active_levels_per_sample: percentile_u64(&self.active_levels_samples, 0.95),
            max_active_levels: self
                .active_levels_samples
                .iter()
                .copied()
                .max()
                .unwrap_or(0),
            avg_reserved_levels_per_sample: average_u64(&self.reserved_levels_samples),
            max_reserved_levels: self
                .reserved_levels_samples
                .iter()
                .copied()
                .max()
                .unwrap_or(0),
            avg_spare_capacity_per_sample: average_u64(&self.spare_capacity_samples),
            max_spare_capacity: self
                .spare_capacity_samples
                .iter()
                .copied()
                .max()
                .unwrap_or(0),
            avg_utilization_per_sample: average_f64(&self.utilization_samples),
        }
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    let commit_id = git_commit_id();
    let layout = L2VecBook::diagnostic_layout_stats();
    let stream = stream_deltas(
        &args.dataset,
        DEFAULT_CHUNK_SIZE,
        None,
        None,
        None,
        args.limit,
    )
    .with_context(|| format!("failed to stream dataset {}", args.dataset.display()))?;
    let mut book: Option<L2VecBook> = None;
    let mut operations = OperationAccumulator::default();
    let mut bids = SideAccumulator::default();
    let mut asks = SideAccumulator::default();
    let mut total_deltas = 0usize;
    let mut total_chunks = 0usize;
    let mut sample_count = 0usize;
    let mut peak_snapshot = L2VecBook::new_l2("BTCUSDT.BINANCE".into()).diagnostic_snapshot();
    let mut peak_total_active_levels = 0_u64;

    for deltas in stream {
        let deltas = deltas.context("failed to decode delta chunk")?;
        if deltas.is_empty() {
            continue;
        }

        total_chunks += 1;
        let book_ref = book.get_or_insert_with(|| L2VecBook::new(deltas[0].instrument_id));

        for delta in &deltas {
            let probe = book_ref.probe_delta(delta)?;
            operations.observe(&probe);
            book_ref.apply_delta(delta)?;
            total_deltas += 1;

            if args.sample_every > 0 && total_deltas % args.sample_every == 0 {
                let snapshot = book_ref.diagnostic_snapshot();
                observe_snapshot(&snapshot, &mut bids, &mut asks);
                sample_count += 1;

                let total_active_levels = snapshot.bids.active_levels + snapshot.asks.active_levels;
                if total_active_levels >= peak_total_active_levels {
                    peak_total_active_levels = total_active_levels;
                    peak_snapshot = snapshot;
                }
            }
        }
    }

    let final_snapshot = book
        .as_ref()
        .map(L2VecBook::diagnostic_snapshot)
        .unwrap_or_else(|| L2VecBook::new_l2("BTCUSDT.BINANCE".into()).diagnostic_snapshot());
    if sample_count == 0 {
        observe_snapshot(&final_snapshot, &mut bids, &mut asks);
        sample_count = 1;
        peak_snapshot = final_snapshot.clone();
    }

    let report = DiagnosticReport {
        timestamp_utc: Utc::now().to_rfc3339(),
        commit_id,
        dataset: args.dataset.display().to_string(),
        limit: args.limit,
        sample_every_deltas: args.sample_every,
        layout,
        replay_shift: ReplayShiftReport {
            total_deltas,
            total_chunks,
            sample_count,
            final_snapshot,
            peak_snapshot,
            operations: operations.summarize(total_deltas),
            bids: bids.summarize(),
            asks: asks.summarize(),
        },
    };

    let rendered = serde_json::to_string_pretty(&report)?;
    if let Some(output) = args.output {
        if let Some(parent) = output.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }
        fs::write(&output, rendered)
            .with_context(|| format!("failed to write {}", output.display()))?;
    } else {
        println!("{rendered}");
    }

    Ok(())
}

fn observe_snapshot(
    snapshot: &L2VecDiagnosticSnapshot,
    bids: &mut SideAccumulator,
    asks: &mut SideAccumulator,
) {
    bids.observe(
        snapshot.bids.active_levels,
        snapshot.bids.reserved_levels,
        snapshot.bids.spare_capacity,
    );
    asks.observe(
        snapshot.asks.active_levels,
        snapshot.asks.reserved_levels,
        snapshot.asks.spare_capacity,
    );
}

fn classify_position(
    counts: &mut PositionCounts,
    index: Option<usize>,
    len_before: usize,
    inserting: bool,
) {
    let Some(index) = index else {
        return;
    };

    let is_tail = if inserting {
        index == len_before
    } else {
        index + 1 == len_before
    };

    if index == 0 {
        counts.head += 1;
    } else if is_tail {
        counts.tail += 1;
    } else {
        counts.middle += 1;
    }
}

fn shift_bucket_index(shifted_levels: usize) -> usize {
    match shifted_levels {
        0 => 0,
        1..=4 => 1,
        5..=16 => 2,
        17..=64 => 3,
        65..=256 => 4,
        257..=1024 => 5,
        _ => 6,
    }
}

fn average_u64(values: &[u64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values
            .iter()
            .copied()
            .map(|value| value as f64)
            .sum::<f64>()
            / values.len() as f64
    }
}

fn average_f64(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().copied().sum::<f64>() / values.len() as f64
    }
}

fn percentile_u64(values: &[u64], quantile: f64) -> u64 {
    if values.is_empty() {
        return 0;
    }

    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    let idx = ((sorted.len() - 1) as f64 * quantile).round() as usize;
    sorted[idx]
}

fn git_commit_id() -> String {
    Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|stdout| stdout.trim().to_string())
        .filter(|stdout| !stdout.is_empty())
        .unwrap_or_else(|| "unknown".to_string())
}
