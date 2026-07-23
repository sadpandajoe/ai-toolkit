# Create-Feature Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `create-feature`, add the
following human-readable phase below it:

```markdown
- Phase: input / complexity-gate / plan-mode / plan-md-write / review-iterations / action-gate / implement-and-review / summarize
```

No additional workflow fields beyond the phase enum are required.

When `Active plan: PLAN.md` is set, resuming sessions can read PROJECT.md alone for orientation — only load PLAN.md if the next phase requires it (review iterations or implementation slice).

Put where-we-left-off details and durable learnings in the Development Log.
