# /watch-pr Continuation Checkpoint Extension

`/checkpoint` writes the generic `## Continuation Checkpoint` block (see [../SKILL.md](../SKILL.md) and [../../../commands/checkpoint.md](../../../commands/checkpoint.md)). When the detected top-level command is `/watch-pr`, append these additional fields to the `### Workflow` block:

```markdown
- Phase: preflight / iterate / terminal
- Manifest: WATCH.md
- PR: #[number] ([head] ← [base])
```

The `Phase` line replaces the generic `Phase:` field with the `/watch-pr`-specific enum.

All loop state — iteration count, green streak, rerun/comment ledgers, comment cursor, escalations — lives in WATCH.md; do not duplicate any of it into the checkpoint. Resuming sessions read PROJECT.md for the pointer, then WATCH.md `## State` for where to continue.

Threshold stops (`Checkpoint saved. Run /clear, then /start to resume the watch.`) and scheduled re-runs are routine watch operation, not interruptions: the watch ends only when WATCH.md `Status` is `stable`, `escalated`, or `blocked`. On resume, re-emit the `## Watch Started` authorization block before the first new iteration — the standing grant must be visible in every session that acts on it.
