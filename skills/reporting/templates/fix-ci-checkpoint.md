# Fix-CI Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `fix-ci`, add this
human-readable phase below it:

```markdown
- Phase: gather-logs / classify / ownership-check / complexity-gate / rca / gate / apply / verify / review / summarize
```

No additional Workflow fields. Failure classification, gate result, review status, and files changed belong in `## Current Status`.
