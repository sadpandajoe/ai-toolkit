---
name: metrics-emit
description: Use to append one structured metrics event after an end-to-end workflow summary. Do NOT use during partial phases, read-only utilities, or workflows that have not reached their terminal report.
---

# Metrics Emit

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Append one JSON line to `.ai-toolkit/metrics.jsonl` at the end of a workflow's
summary step. Provider-neutral, advisory, never blocking.

## Fields

From the routing snapshot and the run:

- `command`: the workflow name (legacy key retained)
- `complexity`: `trivial`, `standard`, or `complex`; `size`: `S`..`XL`;
  `shape`: `single_phase`, `batched`, or `multi_phase`; `phases`: count
- `status`: terminal gate status or workflow-specific outcome
- `gates`: `{ "<gate>": {"status": ..., "attempts": n} }` per gate
- `retries`, `escalations`, `reclassifications`: counts
- `review`: `{ "lane": "codex/sol | claude/opus | same-provider", "raised": n,
  "accepted": n, "delta_reopened": n, "deep_lenses": [...],
  "lanes": { "<lane or lens>": {"raised": n, "accepted": n, "converged": n,
  "confirmed": n, "refuted": n} }, "demoted": [...] }` — `lanes` is what the
  yield thresholds in `rules/code-review.md` read
- `workers`: `{ "<agent or route>": count }` and `premium_calls` (planning,
  deep-review, deep-rca, rca)
- `observations`: count of observation lines written this run

Omit unknown values rather than guessing.

## Steps

1. Build the event with `timestamp` (ISO 8601) and the fields above.
2. Append one strict-JSON line; create the file if needed.
3. On any failure, note it in conversation and continue; metrics never gate
   progress.

```markdown
## Metrics Recorded
Event: <workflow> | Status: <outcome> | File: .ai-toolkit/metrics.jsonl
```

The `metrics` workflow aggregates these into pass rates, retries and
escalations, reclassification rate, reviewer yield, and premium-model share by
phase.
