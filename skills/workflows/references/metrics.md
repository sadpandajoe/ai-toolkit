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

Every event carries an `event` field (`workflow-summary` when absent, for
events recorded before that field existed — see
[`metrics-emit`](../../metrics-emit/SKILL.md)'s Event Types). From the
filtered events, compute:

**Pass rates**: percentage of `workflow-summary` events ending in each status (`clean`, `blocked`, `user-decision`, `skipped`, `micro-fix`)

**Round counts**: average and max review rounds per workflow, from `workflow-summary` events

**Worker usage**: total subagent/worker invocations by role or reasoning tier when recorded, from `workflow-summary` events

**Complexity gate accuracy**: ratio of TRIVIAL classifications that ended `clean` without re-classification (indicates the gate is correctly identifying easy work) — from `workflow-summary` events, or from `complexity` events (`value: TRIVIAL`) paired with a later `complexity` event with `reclassified: true` for the same run, when present

**Gate retry/escalation rate**: from `gate` events, grouped by `gate` name — the fraction of `state: RETRY` and `state: ESCALATE` per gate. High escalation rate on one named gate signals a gate that's failing the same way repeatedly, not a healthy retry loop

**Reclassification rate**: fraction of runs (grouped by `command`) that ever emit a `complexity` event with `reclassified: true`, or a `gate` event with `state: RECLASSIFY`

**Workflow frequency**: how often each workflow is used

Not every workflow emits the mid-run event types yet — treat their absence
for a given `command` as "not instrumented," not as zero retries/
reclassifications.

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
- Reclassification rate: [N] ([%] of total runs) — omit this line if no run in the period emits `complexity`/`gate` events

### Gate Reliability
| Gate | PASS | RETRY | ESCALATE | Escalation % |
|------|------|-------|----------|---------------|
| [gate name] | [N] | [N] | [N] | [%] |

Omit this section entirely if no `gate` events exist in the period —
distinct from a gate table showing 0% escalation, which means it's
instrumented and healthy.

### Trends
- [Notable patterns: improving/declining pass rate, command with high blocked rate, etc.]
- [If insufficient data for trends: "Not enough data for trend analysis (need 10+ events)"]
```

## Notes
- This is a read-only workflow — it never modifies the metrics file
- Metrics are best-effort: not every workflow emits metrics yet (initial adoption covers `create-feature`, `fix-bug`, `fix-ci`)
- The `.ai-toolkit/metrics.jsonl` file is user-local and not committed to git
- Events are appended by [`metrics-emit/`](../../metrics-emit/SKILL.md) at each workflow's summary step, and optionally mid-run via its `gate`/`phase`/`complexity`/`model` event types
- Gate reliability and reclassification rate are only as complete as adoption of the mid-run event types — a gate/skill that only emits `workflow-summary` won't show up in the Gate Reliability table yet
- Trend analysis requires at least 10 events to be meaningful
