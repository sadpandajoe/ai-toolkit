# Review-Plan Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `review-plan`, add this
human-readable phase below it:

```markdown
- Phase: read-plan / choose-mode / validate / revise / record / summarize
```

No additional Workflow fields. The validator lane, its verdict, and the revision count belong in `## Current Status`.
