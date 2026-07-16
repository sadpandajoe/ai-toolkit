# Run-Test-Plan Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `run-test-plan`, add this
human-readable phase below it:

```markdown
- Phase: resolve-plan / review-plan / execute / capture-evidence / report / summarize
```

No additional Workflow fields beyond the phase enum. Plan score, execution counts, and evidence status belong in `## Current Status` (Done / In Progress / Next / Blocked), not on the checkpoint header.
