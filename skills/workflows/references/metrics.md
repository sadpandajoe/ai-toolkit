# Workflow Metrics Summary

> **When**: You want to understand how your workflows are performing — pass rates, retries and escalations, worker usage, reviewer yield, and trends.
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

1. Run `bin/aitk metrics [--period <7d | 30d | all>] [--command <workflow>]`.
   It reads `.ai-toolkit/metrics.jsonl` (the legacy `.claude/metrics.jsonl`
   only when that file is missing), filters, and prints the Metrics Summary:
   workflow usage by terminal status, retries and escalations, worker usage,
   the complexity gate's trivial accuracy, and a trend note.
2. Present the output. Add one or two trend observations when there are 10 or
   more events: a workflow with a high `ESCALATE` or `BLOCKED` rate, or a
   changing `PASS` rate. With `--json`, the same numbers come back as data.

## Notes
- This is a read-only workflow — it never modifies the metrics file
- Metrics are best-effort: only workflows whose summary step ran `bin/aitk metrics emit` appear here
- The `.ai-toolkit/metrics.jsonl` file is user-local and not committed to git
