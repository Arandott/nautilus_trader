# Phase 1 Measurement Handoff

Date: 2026-04-09

## Purpose

This note translates the Phase 0 freeze into a concrete Phase 1 measurement brief.

The rule for Phase 1 is simple:

- do not optimize `L2GridBook` first
- measure until the main memory and performance suspects are ranked by evidence

## Questions Phase 1 Must Answer

Phase 1 should not end until it can answer these with evidence rather than intuition:

1. What is the dominant memory source in the current `L2GridBook` implementation?
2. What is the dominant replay-time performance source?
3. Which parts of the current slowdown are structural, and which parts still look implementation-specific?
4. Which optimization ideas deserve Phase 3 time, and which ones should be dropped early?

## Required Evidence

At minimum, the Phase 1 memo should produce the following artifacts.

### Memory accounting

- byte estimate for `GridLevel`
- byte estimate for `Option<GridLevel>`
- byte estimate for `GridPage`
- byte estimate for `SideGrid`
- page-level overhead split:
  - fixed page body
  - occupancy metadata
  - per-active-level effective cost under different occupancy assumptions

### Occupancy and sparsity evidence

- active page count per side during replay
- active slots per page distribution
- average and percentile occupancy for populated pages
- whether most pages are nearly empty, moderately full, or locally dense

### Operation-path evidence

- update existing level cost
- insert new level cost
- delete existing level cost
- `best_bid_ask` cost
- `top_n_levels` cost for at least one shallow and one deeper query depth

### Root-cause ranking

Each major suspect should be ranked by:

- expected upside
- implementation risk
- validation cost

Example suspects to rank:

- fixed `GridPage` footprint
- `Option<GridLevel>` representation
- storing full `Price` inside each occupied slot
- `BTreeMap<PageId, GridPage>` index overhead
- delete-best repair path
- current `PAGE_SIZE = 64`

## Recommended Execution Order

Phase 1 should proceed in this order.

1. Static structure accounting.
   - Read the current structs and estimate bytes before running new measurements.
   - If easy and low-risk, confirm with `std::mem::size_of` style probes.

2. Replay-time occupancy capture.
   - Instrument page count, active slot count, and occupancy distribution under the current authoritative replay dataset.
   - This is the first hard filter on whether the grid density hypothesis even has room to succeed.

3. Targeted path timing.
   - Reconcile criterion signals with replay intuition.
   - Insert, delete, and best-repair paths deserve special attention because they already look weak in the frozen baseline.

4. Optimization shortlist.
   - Keep the shortlist small.
   - If a candidate has weak upside or unclear validation, do not promote it into Phase 3.

## Early-Stop Conditions Inside Phase 1

Phase 1 should stop and escalate if any of the following happens:

- occupancy data shows overwhelmingly sparse pages and no realistic target workload suggests otherwise
- most of the memory blow-up comes from fixed page bodies, and removing it would require redesign beyond this task boundary
- the main replay pain cannot be separated into a small set of suspects

If any of those hold, write it down clearly rather than forcing a fake optimization phase.

## Suggested Output Files For Phase 1

Phase 1 should ideally leave behind:

- a bottleneck memo
- one or more small supporting measurement outputs
- a shortlist table with keep/drop decisions

Good output names would be:

- `2026-04-09_phase1_bottleneck_memo.md`
- `2026-04-09_phase1_occupancy_snapshot.md`
- `2026-04-09_phase1_optimization_shortlist.md`

## Relationship To The Authoritative Baseline

Phase 1 measurements do not automatically replace the authoritative baseline.

Even if Phase 1 generates new diagnostic outputs:

- keep `all_books_subset_10m_r3_q100_q1000` as the authoritative comparison set
- treat Phase 1 outputs as evidence for prioritization, not as final verdicts

Only a later integrated comparison should supersede the frozen Phase 0 baseline.
