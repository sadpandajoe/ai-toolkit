# Review-Plan Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `review-plan`, add this
human-readable phase below it:

```markdown
- Phase: read-plan / detect-reviewers / review-iterations / cold-read / update / summarize
```

No additional Workflow fields. Reviewers selected, current scores, and revision count belong in `## Current Status`.
