---
tier: Standard
---

# Test PR Report

## Terminal Summary

Use this shape for in-conversation output:

```markdown
## Test-PR Complete

PR: #<number> - <title>
Branch: <head-branch>
App: <url>
Impact: CORE / STANDARD / PERIPHERAL

### Results

| # | Scenario | Tag | Result | Notes |
|---|----------|-----|--------|-------|
| 1 | <name> | [new/fix/guard] | PASS | ... |
| 2 | <name> | [fix] | FAIL | ... |
| 3 | <name> | [guard] | BLOCKED | ... |

### Summary
- <N> passed, <N> failed, <N> blocked of <N> total

### Evidence
- Recording: ~/qa-recordings/<file>.webm (<size>)
- Screenshots: scenario-1-*.png, scenario-2-*.png

### Failures
[Expected, actual, screenshot, console errors]

### Blocked
[Missing auth/data/flag/env details]

### Next Steps
[merge / feed failures back / resolve blockers and rerun]
```

## External Posting

If `--post` was passed, do not paste the terminal table directly into an external destination.

Read [../write-report.md](../write-report.md) for the canonical narrative body. Load destination-specific mechanics only when posting:

- Shortcut: [../../../shortcut/references/report.md](../../../shortcut/references/report.md)
- GitHub PR comment: use the PR comment flow and respect attachment size limits from [../browser-recording.md](../browser-recording.md)

Post forms:

- `--post`: ask where to post after the run.
- `--post sc-12345`: post to that Shortcut story.
- `--post pr`: post to the PR under test.
- `--post sc-12345 --post pr`: post to both.

Attach or link the recording from `~/qa-recordings/`. Transcode when needed before GitHub upload/comment size limits.
