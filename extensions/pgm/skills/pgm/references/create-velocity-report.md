# Monthly Velocity Metrics

Before executing, read the [program management context](../../../rules/pgm.md). Use the [Shortcut collection reference](../../../../../skills/shortcut/references/fetch.md) for API retry, pagination, parsing, and field-shape rules.

> **When**: End of month (or anytime you need historical velocity metrics).
> **Produces**: Full velocity report with throughput, cycle times, PR metrics, and team breakdowns.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../../../rules/durable-workflows.md).
The phase graph, authorization gates, and effect keys are the
`create-velocity-report` entry in `interfaces/contracts.json`; use `bin/aitk
checkpoint --with-pgm` for every durable transition and effect record.

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
- If `--summary-only`, skip to Step 5

### 2. Read Pipeline Instructions

- Read `$PGM_DIR/run.md` for the full pipeline instructions
- Follow those instructions — they are the authoritative source for how the pipeline runs

### 3. Execute Pipeline

Follow the steps in `run.md`:

**3a. Start GitHub collection in background:**
```bash
cd $PGM_DIR && python3 collect_github.py
```
This takes ~5-10 min. Continue to 3b while it runs.

**3b. Collect Shortcut data (while GitHub runs in background):**

Use the Shortcut REST API (preferred) via `curl` with `$SHORTCUT_API_TOKEN`.
Follow the Shortcut collection reference for the retry wrapper, JSON parsing, and field shape gotchas.

Run all team queries in **parallel bash calls** — each team's queries are independent:
- **Completed stories** per team: `POST /stories/search` with `completed_at_start`/`completed_at_end` from config date range, `group_id`
- **WIP snapshot** per team: `POST /stories/search` with `workflow_state_types: ["started"]`, `group_id`

That's two independent calls per configured team. Schedule them concurrently when supported and handle pagination on each.

Also collect:
- **Iterations**: overlapping the target month
- **Epics**: for all unique `epic_id` values found in completed stories

Save to `data/{month}/`:
- `raw_stories.json` — all completed stories
- `raw_wip.json` — all WIP stories
- `raw_iterations.json` — iteration objects
- `raw_epics.json` — epic objects

**3c. Wait for GitHub collection to finish.**

**3d. Run processing pipeline sequentially:**
```bash
cd $PGM_DIR && python3 collect_shortcut.py
cd $PGM_DIR && python3 analyze.py
cd $PGM_DIR && python3 report.py
```

### 4. Validate Output

Read `data/{month}/report.md` and `data/{month}metrics.json`.

Flag data quality issues:
- Teams with 0 completed stories (collection may have failed)
- Negative cycle time values (timestamp issues)
- Individual PR counts that seem too high or low vs team size
- Large numbers of unlinked stories/PRs (Shortcut ↔ GitHub linkage gaps)

### 5. Present Report

Read and present `data/{month}/report.md` to the user.

If `--summary-only`: read `data/{month}metrics.json` and produce a concise executive summary using the [communication reference](comms.md) with `executive` audience.

If `--audience <mode>` is provided, format the final output for that audience using the same internal PGM formatting skill.

Suggest follow-up actions:
- "What trends do you see?" → analyze metrics.json for patterns
- "Compare to last month" → read prior month's `data/{prev-month}metrics.json` if it exists
- "Summarize for leadership" → use the internal PGM formatting skill with `executive` audience
- "Who's blocked?" / "Where are the bottlenecks?" → dig into specifics from raw data
- "Break this down by team" → team-level analysis from metrics.json

## Notes

- This wraps the existing Python pipeline in `$PGM_DIR/`
- The pipeline is the authoritative source for metric calculations — don't reimplement metrics manually
- For live/current-state data, use `$pgm create-status-report` instead
- If the pipeline fails, read the error output and diagnose — don't silently skip steps
- Raw data files can be re-analyzed without re-collecting: skip to Step 3d if `raw_*.json` files already exist for the month
