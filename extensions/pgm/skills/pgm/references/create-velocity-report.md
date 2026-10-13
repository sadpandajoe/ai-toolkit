# Monthly Velocity Metrics

Before executing, read the [program management context](../../../rules/pgm.md). Use the [Shortcut collection reference](../../../../../skills/shortcut/references/fetch.md) for API retry, pagination, parsing, and field-shape rules.

> **When**: End of month (or anytime you need historical velocity metrics).
> **Produces**: Full velocity report with throughput, cycle times, PR metrics, and team breakdowns.

## Effect Boundary

Effect: `local_mutation`.

## Usage

```
$pgm create-velocity-report                       # Current month from config.json
$pgm create-velocity-report --month 2026-03       # Specific month
$pgm create-velocity-report --summary-only        # Exec summary from existing metrics.json
$pgm create-velocity-report --audience executive  # Format for a specific audience
```

## Steps

### 1. Prepare and Preflight

- Run `bin/aitk pgm-preflight --workflow create-velocity-report --pgm-dir
  "$PGM_DIR"`, adding connector flags only for capabilities that are actually
  available. On any nonzero result, stop before collection with zero report
  effects.
- Read `$PGM_DIR/config.json` for current `month`, `date_range`, teams, members, repos
- If `--month` provided and differs from config, tell the user to update `config.json` first (the pipeline reads config directly)
- If `--summary-only`, skip to Step 4

### 2. Run the Pipeline

After `bin/aitk pgm-preflight` passes, follow `$PGM_DIR/run.md`: it is the
authoritative source for how the pipeline collects, processes and reports.
When `raw_*.json` files already exist for the month, re-run only the
processing steps instead of collecting again.

### 3. Validate Output

Read `report.md` and `metrics.json` in `data/{month}/`.

Flag data quality issues:
- Teams with 0 completed stories (collection may have failed)
- Negative cycle time values (timestamp issues)
- Individual PR counts that seem too high or low vs team size
- Large numbers of unlinked stories/PRs (Shortcut ↔ GitHub linkage gaps)

### 4. Present Report

Read and present `data/{month}/report.md` to the user.

If `--summary-only`: read `metrics.json` in `data/{month}/` and produce a concise executive summary using the [communication reference](comms.md) with `executive` audience.

If `--audience <mode>` is provided, format the final output for that audience
with [comms.md](comms.md).

Suggest follow-ups: trends from `metrics.json`, a comparison with the
previous month's `metrics.json` when it exists, a leadership summary through
[comms.md](comms.md), bottlenecks from the raw data, or a per-team breakdown.

## Notes

- The pipeline is the authoritative source for metric calculations; don't
  reimplement metrics manually.
- For live/current-state data, use `$pgm create-status-report` instead.
- If the pipeline fails, read the error output and diagnose; don't silently
  skip steps.
