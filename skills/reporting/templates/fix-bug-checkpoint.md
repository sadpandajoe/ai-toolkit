# Fix-Bug Continuation Details

The deterministic checkpoint API owns the machine block in
[workflow-checkpoint.md](workflow-checkpoint.md). For `fix-bug`, add these
human-readable fields below it:

```markdown
- Phase: input / complexity-gate / existing-fix-check / plan-mode / plan-md-write / implement-and-review / qa-validate / summarize
- Existing-fix status: FIXED_UPSTREAM | FIX_PENDING_PR | UNFIXED | SKIPPED | pending
```

The `Existing-fix status:` line follows the phase.

When `Active plan: PLAN.md` is set, resuming sessions can read PROJECT.md alone for orientation — only load PLAN.md if the next phase requires it (implementation or QA validation).

Put where-we-left-off details and durable learnings in the Development Log.
