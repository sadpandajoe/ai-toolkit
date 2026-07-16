# Update-Tests Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `update-tests`, add this
human-readable phase below it:

```markdown
- Phase: scope / gap-analysis / update-tests / verify / review / commit / summarize
```

No additional Workflow fields. Existing-suite status, files changed, and verification status belong in `## Current Status`.
