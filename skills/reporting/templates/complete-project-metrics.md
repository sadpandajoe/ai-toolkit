# complete-project Metrics Summary Template

Filter `.ai-toolkit/metrics.jsonl` events to those relevant to this project (timestamp range or referenced workflows), then aggregate. Fall back to legacy `.claude/metrics.jsonl` only when the canonical file does not exist.

```markdown
## Project Metrics Summary

| Metric | Value |
|--------|-------|
| Total commands run | [N] |
| Pass rate (`PASS`) | [N%] |
| Escalated / user decisions / blocked | [N] / [N] / [N] |
| Gate retries / escalations | [N] / [N] |
| Complexity distribution | [N] trivial / [N] standard / [N] complex |
| Review yield (accepted / raised per lane) | independent [N/N], second-family [N/N], deep lenses [N/N] |
| Worker usage | [agent or route]: [N] |

### Command Breakdown
| Command | Runs | PASS | ESCALATE | BLOCKED |
|---------|------|------|----------|---------|
| [name] | [N] | [N] | [N] | [N] |
```

If no metrics file exists or no events found in range, emit `No metrics recorded for this project` and continue.
