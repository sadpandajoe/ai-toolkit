# Watch-PR Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `watch-pr`, add these
human-readable fields below it:

```markdown
- Phase: preflight / iterate / terminal
- Manifest: WATCH.md
- PR: #[number] ([head] ← [base])
```

The `Phase` line records the current watch phase.

All loop state — iteration count, green streak, rerun/comment ledgers, comment cursor, escalations — lives in WATCH.md; do not duplicate any of it into the checkpoint. Resuming sessions read PROJECT.md for the pointer, then WATCH.md `## State` for where to continue.

Threshold resets and recurrence are routine watch operation, not interruptions:
the watch ends only when WATCH.md `Status` is `stable`, `escalated`, or
`blocked`. On resume, re-emit the `## Watch Started` authorization block before
the first effect.
