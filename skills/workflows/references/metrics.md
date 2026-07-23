# Workflow Metrics Summary

> **When**: You want to understand how your workflows are performing — pass rates, review round counts, worker usage, and trends.
> **Produces**: Aggregate summary from `.ai-toolkit/metrics.jsonl`.

## Effect Boundary

Effect: `read_only`.

## Usage

```
metrics                    # Summary of all recorded workflows
metrics --period 7d        # Last 7 days only (also: 30d, all)
metrics --command fix-bug  # Filter to a specific command
```

## Steps

### 1. Read Metrics File

Read `.ai-toolkit/metrics.jsonl`. During migration, read legacy `.claude/metrics.jsonl` only when the canonical file does not exist; never write new events to the legacy path. If neither file exists or the selected file is empty:
```markdown
No metrics recorded yet. Metrics are emitted automatically when workflows complete.
Run a workflow (e.g., `create-feature`, `fix-bug`) to start collecting data.
```
Stop.

### 2. Filter Events

Apply filters from arguments:
- `--period <duration>`: filter to events within the specified window (default: `all`)
  - `7d` = last 7 days, `30d` = last 30 days, `all` = no filter
- `--command <name>`: filter to events matching the workflow identifier (legacy flag name retained for compatibility)

### 3. Compute Aggregates

From the filtered events, compute:

**Pass rates**: percentage of workflows ending in each status (`clean`, `blocked`, `user-decision`, `skipped`, `micro-fix`)

**Round counts**: average and max review rounds per workflow

**Worker usage**: total subagent/worker invocations by role or reasoning tier when recorded

**Complexity gate accuracy**: ratio of TRIVIAL classifications that ended `clean` without re-classification (indicates the gate is correctly identifying easy work)

**Workflow frequency**: how often each workflow is used

### 4. Emit Summary

```markdown
## Metrics Summary

Period: [7d / 30d / all]
Events: [total count]

### Workflow Usage
| Workflow | Runs | Clean | Blocked | Other |
|---------|------|-------|---------|-------|
| [name] | [N] | [N] | [N] | [N] |

### Review Rounds
| Workflow | Avg Rounds | Max Rounds |
|---------|------------|------------|
| [name] | [N.N] | [N] |

### Worker Usage
| Worker / Tier | Invocations | % |
|-------|-------------|---|
| [name or tier] | [N] | [%] |

### Complexity Gate
- Trivial workflows: [N] ([%] of total)
- Trivial → clean: [N] ([accuracy %])

### Trends
- [Notable patterns: improving/declining pass rate, command with high blocked rate, etc.]
- [If insufficient data for trends: "Not enough data for trend analysis (need 10+ events)"]
```

## Notes
- This is a read-only workflow — it never modifies the metrics file
- Metrics are best-effort: not every workflow emits metrics yet (initial adoption covers `create-feature`, `fix-bug`, `fix-ci`)
- The `.ai-toolkit/metrics.jsonl` file is user-local and not committed to git
- Events are appended by [`metrics-emit/`](../../metrics-emit/SKILL.md) at each workflow's summary step
- Trend analysis requires at least 10 events to be meaningful
