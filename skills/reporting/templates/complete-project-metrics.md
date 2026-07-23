# complete-project Metrics Summary Template

Filter `.ai-toolkit/metrics.jsonl` events to those relevant to this project (timestamp range or referenced workflows), then aggregate. Fall back to legacy `.claude/metrics.jsonl` only when the canonical file does not exist.

```markdown
## Project Metrics Summary

| Metric | Value |
|--------|-------|
| Total commands run | [N] |
| Pass rate (clean/micro-fix) | [N%] |
| Blocked/failed | [N] |
| Average review rounds | [N.N] |
| Complexity distribution | [N] trivial / [N] moderate / [N] standard |
| Worker usage | [role/tier]: [N] |

### Command Breakdown
| Command | Runs | Clean | Blocked |
|---------|------|-------|---------|
| [name] | [N] | [N] | [N] |
```

If no metrics file exists or no events found in range, emit `No metrics recorded for this project` and continue.
