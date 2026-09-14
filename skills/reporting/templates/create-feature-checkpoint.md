# Create-Feature Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `create-feature`, add the
following human-readable phase below it:

```markdown
- Phase: intake / classify / scope / plan / validate / implement / verify / review / validate-behavior / integrated-review / summarize
- Snapshot: <complexity>/<size>/<shape>, phase <n> of <total> (from `bin/aitk project-state show`)
```

No additional workflow fields beyond the phase enum are required.

When `Active plan: PLAN.md` is set, resuming sessions can read PROJECT.md alone for orientation — only load PLAN.md if the next phase requires it (plan validation or an implementation unit).

Put where-we-left-off details and durable learnings in the Development Log.
