---
name: recover-git-state
description: Recover from a failed Git operation or mistaken repository mutation with the least destructive effective action.
---

# Recover Git State

Use this reference only after something has gone wrong. Recovery does not
broaden authorization: inspect first, resolve exact targets, and ask before any
step that can discard commits, tracked changes, or untracked files.

## Recovery Ladder

| Level | Goal | Examples |
|---|---|---|
| Safe | Understand the state and create a rollback point | `git status`, targeted `git diff`, `git reflog`, a rescue branch, or a verified stash including needed untracked files |
| Moderate | Undo one bounded operation or restore explicit paths | the matching `--abort` command, or `git restore --source=<known-commit> -- <explicit-path>` after preserving current work |
| Nuclear | Replace broad working state or delete untracked files | `git reset --hard <verified-commit>` or `git clean -fd` only after a dry run, exact-scope review, rollback capture, and explicit confirmation |

Always start at Safe and escalate only when the lower level cannot recover the
intended state.

## Procedure

1. Stop the failing operation. Record what happened in PROJECT.md when a
   durable workflow is active.
2. Inspect `git status`, the relevant diff, recent commits, and `git reflog`.
   Identify the exact known-good commit and paths; do not use a broad directory,
   unresolved variable, or glob as a destructive target.
3. Preserve recoverable work with a rescue branch or another verified rollback
   point. Confirm that tracked and needed untracked files are represented.
4. Prefer the operation-specific abort (`merge`, `rebase`, `cherry-pick`, or
   revert) when it restores the pre-operation state without discarding unrelated
   work.
5. Before a destructive reset or clean, show the exact target and impact. Run
   `git clean -nd` before any clean. Proceed only with explicit authorization.
6. Re-run `git status`, inspect the resulting diff/history, and execute the
   smallest relevant verification. Record whether recovery succeeded and what
   remains.

Stop and escalate when the known-good state is uncertain, recovery attempts are
making the repository worse, data loss may exceed the approved scope, or the
failure has production or security implications.
