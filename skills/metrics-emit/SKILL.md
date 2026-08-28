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
- `total_tokens` — total input+output+cache tokens spent across every model/route call this run made, summed across all reasoning tiers (`rules/model-assignment.md`'s §17 efficiency measure)
- `premium_tokens` — the subset of `total_tokens` spent on a premium route: any call routed to `opus` or a Codex `sol` model (per `interfaces/model-routing.json`'s `providers`), as opposed to the `sonnet` control-plane default
- `retries` — count of this run's gate checkpoints that resolved `RETRY` or `ESCALATE` (`rules/gates.md`'s six-state contract) — the same count `gate` events let `metrics` reconstruct per-gate, offered here pre-summed per run
- `reclassifications` — count of `rules/complexity-gate.md` reclassifications this run recorded (each paired with a `bin/aitk checkpoint record-reclassification` call)
- `reviewer_yield` — for a run with an independent-review step (`code-review`, or any goal skill's SOL review phase): confirmed findings ÷ findings raised, as a decimal between 0 and 1 (omit for runs with no review step, or when the reviewer raised zero findings — not 0, which would misreport a review that found nothing wrong as a review that produced no signal)

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
  "worker_usage": {},
  "total_tokens": <number>,
  "premium_tokens": <number>,
  "retries": <number>,
  "reclassifications": <number>,
  "reviewer_yield": <decimal 0-1>
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
- `reason` — the short, stable failure-reason string passed to `decide_failure()` (omit for `PASS`; required for `RETRY`/`ESCALATE` — this is what `reflection`'s drift-detection groups by)
- `kind` — `mechanical` or `reasoning`, the failure-kind passed to `decide_failure(kind=...)` (omit for `PASS`)
- `repeat_count` — the value `decide_failure()` returned alongside `state`, when applicable (omit for `PASS`)

```json
{"event": "gate", "timestamp": "<ISO 8601>", "command": "<command-name>", "gate": "<gate-name>", "state": "<GATE_STATE>", "reason": "<failure-reason>", "kind": "<mechanical|reasoning>", "repeat_count": <number>}
```

`RETRY` and `ESCALATE` are both recorded through this one event type,
distinguished by `state` — they are the same signal at different repeat
counts (`rules/gates.md`'s counting rule), not separate event shapes.
`reason` is what makes two failures "the same" for that counting rule and is
what `skills/reflection/SKILL.md`'s `(gate, reason)` grouping reads; without
it reflection has nothing to group by.

### `phase`

One event per phase transition within a durable workflow (e.g. `create-feature`'s prepare → plan → implement → verify → report).

- `command` — the canonical workflow identifier
- `phase` — the phase name entered
- `execution_shape` — `SINGLE_PHASE` or `MULTI_PHASE`, when the workflow has already classified shape (omit otherwise)

```json
{"event": "phase", "timestamp": "<ISO 8601>", "command": "<command-name>", "phase": "<phase-name>", "execution_shape": "<SINGLE_PHASE|MULTI_PHASE>"}
```

### `complexity`

One event per complexity classification or reclassification decision.

- `command` — the canonical workflow identifier
- `value` — `TRIVIAL`, `STANDARD`, or `COMPLEX`
- `size` — `XS`, `S`, `M`, `L`, or `XL`, when the workflow classifies size (omit otherwise)
- `reclassified` — `true` if this replaces an earlier classification for the same run, omit otherwise

```json
{"event": "complexity", "timestamp": "<ISO 8601>", "command": "<command-name>", "value": "<TRIVIAL|STANDARD|COMPLEX>", "size": "<XS|S|M|L|XL>", "reclassified": true}
```

### `model`

One event per model/route selection, when the provider binding makes the resolved route visible to the calling skill.

- `command` — the canonical workflow identifier
- `role` — the route's name (e.g. `implementation`, `rca`, `review`)
- `model` — the resolved model identifier
- `input_tokens`, `output_tokens`, `cache_tokens` — this call's token usage, when the provider binding surfaces it (omit any or all when the runtime doesn't report them — most CLI-transport calls won't); `workflow-summary`'s `total_tokens`/`premium_tokens` are the per-run sums a workflow reports regardless of whether the individual `model` events carry these fields

```json
{"event": "model", "timestamp": "<ISO 8601>", "command": "<command-name>", "role": "<route-name>", "model": "<model-id>", "input_tokens": <number>, "output_tokens": <number>, "cache_tokens": <number>}
```

### `observation`

One event per correction signal worth learning from — a moment where the
workflow's own behavior turned out to be wrong and got fixed, not a normal
gate failure or classification. Emitted only from an existing checkpoint
already reached in the course of the workflow — a gate outcome
(`rules/gates.md`), a reclassification (`bin/aitk checkpoint
record-reclassification`), or a workflow's terminal `workflow-summary` step.
There is no hook and no always-on observer watching for these; if none of
those three steps notices the correction, no event is emitted for it.

- `kind` — one of `user-correction` (the user explicitly redirected a wrong
  approach), `skill-misroute` (the wrong skill/command handled the request),
  `reclassify` (a `rules/complexity-gate.md` reclassification — pair with the
  `record-reclassification` call at the same step), `gate-repeat` (a gate hit
  `RETRY`/`ESCALATE` more than once for the same reason), `plan-invalidated`
  (an accepted RCA, decomposition, or phase plan had to be thrown out),
  `manual-workaround` (the workflow had to route around a missing or broken
  capability by hand)
- `skill` — the canonical skill/workflow name the observation is about
- `phase` — the phase or step the correction happened in
- `issue` — one line describing what went wrong
- `suggested_change` — one line describing what should change to prevent it
- `principle` — optional; a `rules/*.md` principle the issue relates to, when
  identifiable
- `status` — `OPEN` when first recorded; a follow-up event with the same
  `ref` records `ACTIONED` or `DECLINED` once `skills/reflection` (or a
  human) disposes of it
- `ref` — optional; present only on an `ACTIONED`/`DECLINED` follow-up event,
  pointing back to the originating observation (e.g. its timestamp)

```json
{"event": "observation", "timestamp": "<ISO 8601>", "kind": "<user-correction|skill-misroute|reclassify|gate-repeat|plan-invalidated|manual-workaround>", "skill": "<skill-name>", "phase": "<phase-name>", "issue": "<one line>", "suggested_change": "<one line>", "principle": "<rules/*.md pointer>", "status": "OPEN"}
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
- Mid-run event types (`gate`, `phase`, `complexity`, `model`, `observation`) are optional and additive — a workflow that only ever emits `workflow-summary` is still fully compliant; they exist so per-checkpoint telemetry (gate retry/escalation rates, reclassification frequency) doesn't have to be reconstructed from a single end-of-run event
- The `metrics` workflow reads this file and produces aggregate summaries
- `skills/reflection` reads `observation` and `gate` events to cluster recurring corrections into proposals — see that skill for how `OPEN` observations get disposed of
