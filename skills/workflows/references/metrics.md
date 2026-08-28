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

**Reclassification rate**: fraction of runs (grouped by `command`) that ever emit a `complexity` event with `reclassified: true`, or a `gate` event with `state: RECLASSIFY` — or, cheaper when present, that report a nonzero `workflow-summary.reclassifications`

**Workflow frequency**: how often each workflow is used

**Token usage**: total and premium tokens per run, from `workflow-summary`'s `total_tokens`/`premium_tokens`. When a run has no `workflow-summary` token fields but does have `model` events carrying `input_tokens`/`output_tokens`/`cache_tokens`, sum those instead (`premium` = calls whose `role`/`model` resolve to `opus` or a Codex `sol` model per `interfaces/model-routing.json`). Report the premium share (`premium_tokens / total_tokens`) alongside the totals — §14's rollout hypothesis is a *reduction* in that share over time, not just the raw count.

**Retry count**: average and total `workflow-summary.retries` per workflow — a per-run cross-check against the per-gate RETRY/ESCALATE counts in Gate Reliability below; the two should roughly agree, and a persistent gap means one of the two recording paths is under-instrumented for that workflow.

**Reviewer yield**: average `workflow-summary.reviewer_yield` across runs that report it, grouped by `command`. A falling yield for one workflow means its independent reviewer is raising more noise relative to confirmed findings — worth a `rules/code-review.md` look, not an eval fixture.

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

### Token Usage
| Workflow | Total Tokens | Premium Tokens | Premium % | Avg Retries |
|---------|-------------|-----------------|-----------|-------------|
| [name] | [N] | [N] | [%] | [N.N] |

Omit this section entirely if no run in the period reports `total_tokens`
(from `workflow-summary` or summed `model` events) — distinct from a row
showing 0 premium tokens, which means the run stayed on the Sonnet control
plane the whole way through.

### Reviewer Yield
| Workflow | Avg Yield | Runs Reporting |
|---------|-----------|-----------------|
| [name] | [N.N%] | [N] |

Omit this section entirely if no run in the period reports
`reviewer_yield`.

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
- Token/retry/reclassification/reviewer-yield fields (`skills/metrics-emit/SKILL.md`'s C5 addition) are new and best-effort like every other `workflow-summary` field — expect sparse or absent data until goal skills are updated to report them; treat their absence for a given `command` as "not instrumented," not as zero
- Trend analysis requires at least 10 events to be meaningful
