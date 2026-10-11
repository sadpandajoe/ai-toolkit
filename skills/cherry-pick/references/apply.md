# Cherry-Pick Apply

Use once the gate says the change proceeds.

## Pick

Take the parent count from the pre-flight row's `parents` column
([batch.md](batch.md)); for a single pick, run
`<skill-dir>/scripts/batch-preflight.sh <target-branch> <commit>`. One parent:
`git cherry-pick -x <commit>`. A merge commit takes `-m 1` only when parent 1
is the target-base side; otherwise stop as `Blocked: merge parent ambiguous`.

Excluded files that exist on both branches are reverted after the pick.
Excluded files missing on the target arrive as modify/delete conflicts.

## Modify/Delete Conflicts

1. `git rm <missing-files>`; this is the resolution, not a revert.
2. Verify `.git/CHERRY_PICK_HEAD` still exists.
3. Resolve any content conflicts in other files and stage them.
4. `git cherry-pick --continue`.

Before any `--continue`, `.git/CHERRY_PICK_HEAD` must exist. If it is missing,
do not continue: `git cherry-pick --abort` and re-run from the pick
([gotchas.md](../gotchas.md), "CHERRY_PICK_HEAD missing").

## Escalation Ladder

Follow this order; do not skip steps.

1. **Resolve in place:** `git rm` for modify/delete, edit markers for content
   conflicts, then `git cherry-pick --continue`.
2. **Abort and re-run:** `git cherry-pick --abort`, then
   `git cherry-pick -x <commit>` with a different resolution approach.
3. **Manual commit:** when CHERRY_PICK_HEAD is unrecoverable after the re-run,
   resolve the files, `git commit -C <sha>` (keeps the source author and
   message), then amend in the `(cherry picked from commit <sha>)` line.
4. **`git diff <commit>^..<commit> -- <files> | git apply --3way`:** last
   resort, only when cherry-pick plus `git rm` cannot express the subset. It
   loses the cherry-pick metadata.

Hand off to adapt when a conflict needs code-level adaptation or inferred
source intent; stay in apply for branch switching, the pick, state checks,
staging and `--continue`. After `--continue`, hand off to validation.
