---
name: metrics-emit
description: Use to append one structured metrics event after an end-to-end workflow summary. Do NOT use during partial phases, read-only utilities, or workflows that have not reached their terminal report.
---

# Metrics Emit

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Append a single structured event to `.ai-toolkit/metrics.jsonl` at the end of any workflow's summary step. This is provider-neutral observability infrastructure.

## Event Types

Every event carries an `event` field. `workflow-summary` is the default and
the only type emitted before this section existed — omitting `event`
entirely means `workflow-summary`, so every event recorded before this
extension still reads back the same way. The other types are optional,
finer-grained events a workflow may emit *during* a run, not only at its
terminal summary; each is additive and independent of the others.

### `workflow-summary` (default)

The calling workflow provides these values in its prompt:

- `command` — the canonical workflow identifier (legacy JSON key retained for compatibility; e.g., `create-feature`, `fix-bug`)
- `complexity` — `TRIVIAL`, `STANDARD`, or `COMPLEX` (`aitk.routing.COMPLEXITY_VALUES`; the pre-rename `MODERATE`/lowercase values are stale and must not be emitted)
- `status` — the final outcome: `clean`, `blocked`, `user-decision`, `skipped`, `micro-fix`, or workflow-specific
- `rounds` — number of review iterations (0 if no review loop)
- `gate_decisions` — object with gate outcomes (e.g., `{complexity: "standard", action: "proceed", review: "clean"}`)
- `worker_usage` — object counting subagent/worker usage by runtime-specific effort or model when available

All fields are best-effort. If a value is unknown or not applicable, omit it rather than guessing.

```json
{
  "event": "workflow-summary",
  "timestamp": "<ISO 8601>",
  "command": "<command-name>",
  "complexity": "<TRIVIAL|STANDARD|COMPLEX>",
  "status": "<outcome>",
  "rounds": <number>,
  "gate_decisions": {},
  "worker_usage": {}
}
```

### `gate`

One event per gate checkpoint a workflow passes through — any skill citing
`rules/gates.md`'s six-state contract, not only the four workflows whose
`workflow-summary.gate_decisions` already records the final outcome. Lets
the `metrics` workflow compute retry/escalation rates and reclassification
frequency per gate, not just per whole run.

- `command` — the canonical workflow identifier
- `gate` — the gate's name (e.g. `review`, `rca-confidence`, `scope-audit` — the calling skill's own name for the checkpoint)
- `state` — one of `aitk.gates.GATE_STATES` (`PASS`, `RETRY`, `ESCALATE`, `USER_DECISION`, `BLOCKED`, `RECLASSIFY`)
- `repeat_count` — the value `decide_failure()` returned alongside `state`, when applicable (omit for `PASS`)

```json
{"event": "gate", "timestamp": "<ISO 8601>", "command": "<command-name>", "gate": "<gate-name>", "state": "<GATE_STATE>", "repeat_count": <number>}
```

`RETRY` and `ESCALATE` are both recorded through this one event type,
distinguished by `state` — they are the same signal at different repeat
counts (`rules/gates.md`'s counting rule), not separate event shapes.

### `phase`

One event per phase transition within a durable workflow (e.g. `create-feature`'s prepare → plan → implement → verify → report).

- `command` — the canonical workflow identifier
- `phase` — the phase name entered

```json
{"event": "phase", "timestamp": "<ISO 8601>", "command": "<command-name>", "phase": "<phase-name>"}
```

### `complexity`

One event per complexity classification or reclassification decision.

- `command` — the canonical workflow identifier
- `value` — `TRIVIAL`, `STANDARD`, or `COMPLEX`
- `reclassified` — `true` if this replaces an earlier classification for the same run, omit otherwise

```json
{"event": "complexity", "timestamp": "<ISO 8601>", "command": "<command-name>", "value": "<TRIVIAL|STANDARD|COMPLEX>", "reclassified": true}
```

### `model`

One event per model/route selection, when the provider binding makes the resolved route visible to the calling skill.

- `command` — the canonical workflow identifier
- `role` — the route's name (e.g. `implementation`, `rca`, `review`)
- `model` — the resolved model identifier

```json
{"event": "model", "timestamp": "<ISO 8601>", "command": "<command-name>", "role": "<route-name>", "model": "<model-id>"}
```

## Steps

1. Construct the JSONL event using the shape for the event type being recorded (see Event Types above; default to `workflow-summary` at a workflow's terminal summary step).

2. Append the event as a single line to `.ai-toolkit/metrics.jsonl` (create the file if it does not exist).

3. If the append fails for any reason (file permissions, disk space, path issue), log the failure in conversation but do **not** block or fail the calling workflow. Metrics are advisory — never gate workflow progress on them.

## Output

```markdown
## Metrics Recorded
Event: <workflow-name>
Status: <outcome>
File: .ai-toolkit/metrics.jsonl
```

## Notes
- One line per event, strict JSON — no trailing commas, no multi-line formatting
- The `.ai-toolkit/` directory is user-local and ignored by git
- End-to-end workflows should reference this skill context at the very end of their summary step, after all gates have resolved
- Mid-run event types (`gate`, `phase`, `complexity`, `model`) are optional and additive — a workflow that only ever emits `workflow-summary` is still fully compliant; they exist so per-checkpoint telemetry (gate retry/escalation rates, reclassification frequency) doesn't have to be reconstructed from a single end-of-run event
- The `metrics` workflow reads this file and produces aggregate summaries
