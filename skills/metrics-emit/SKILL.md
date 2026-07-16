---
name: metrics-emit
description: Use to append one structured metrics event after an end-to-end workflow summary. Do NOT use during partial phases, read-only utilities, or workflows that have not reached their terminal report.
---

# Metrics Emit

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Append a single structured event to `.ai-toolkit/metrics.jsonl` at the end of any workflow's summary step. This is provider-neutral observability infrastructure.

## Required Context

The calling workflow provides these values in its prompt:

- `command` — the slash command name (e.g., `create-feature`, `fix-bug`)
- `complexity` — `trivial`, `moderate`, or `standard`
- `status` — the final outcome: `clean`, `blocked`, `user-decision`, `skipped`, `micro-fix`, or workflow-specific
- `rounds` — number of review iterations (0 if no review loop)
- `gate_decisions` — object with gate outcomes (e.g., `{complexity: "standard", action: "proceed", review: "clean"}`)
- `worker_usage` — object counting subagent/worker usage by runtime-specific effort or model when available

All fields are best-effort. If a value is unknown or not applicable, omit it rather than guessing.

## Steps

1. Construct the JSONL event:

```json
{
  "timestamp": "<ISO 8601>",
  "command": "<command-name>",
  "complexity": "<trivial|moderate|standard>",
  "status": "<outcome>",
  "rounds": <number>,
  "gate_decisions": {},
  "worker_usage": {}
}
```

2. Append the event as a single line to `.ai-toolkit/metrics.jsonl` (create the file if it does not exist).

3. If the append fails for any reason (file permissions, disk space, path issue), log the failure in conversation but do **not** block or fail the calling workflow. Metrics are advisory — never gate workflow progress on them.

## Output

```markdown
## Metrics Recorded
Event: <command-name>
Status: <outcome>
File: .ai-toolkit/metrics.jsonl
```

## Notes
- One line per event, strict JSON — no trailing commas, no multi-line formatting
- The `.ai-toolkit/` directory is user-local and ignored by git
- End-to-end command prompts should reference this skill context at the very end of their summary step, after all gates have resolved
- `metrics` command reads this file and produces aggregate summaries
