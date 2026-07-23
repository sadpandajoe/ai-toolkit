---
tier: Heavy
---

# Cherry-Pick Apply

Use once investigation says the change should proceed.

## Pre-Exclusion

When investigation identified files to exclude (CI configs, submodule pointers, files not relevant to the target branch):

1. Build the exclusion list before running `cherry-pick -x`.
2. For small exclusion sets where excluded files **exist on both branches**, proceed with cherry-pick and revert the excluded files after resolution.
3. For excluded files that **don't exist on the target branch**, expect modify/delete conflicts — resolve with `git rm` (see Modify/Delete Conflicts below).
4. Only for large exclusion sets or high-adaptation changes, fall back to `git diff <commit>^..<commit> -- <files-to-include> | git apply --3way`. This is a **last resort** — it discards cherry-pick metadata (`-x` attribution, CHERRY_PICK_HEAD). Use the escalation ladder below first.

## Execution

1. Switch to the target branch.
2. Check whether the commit is a merge commit:
   ```bash
   <skill-dir>/scripts/detect-merge-commit.sh <commit>
   ```
   - 1 parent → `git cherry-pick -x <commit>`
   - 2+ parents → `git cherry-pick -x -m 1 <commit>`
3. Preserve author and source commit metadata.

## Modify/Delete Conflicts

When a cherry-pick touches files that exist on source but not on target, git reports modify/delete conflicts. Resolution path differs from content conflicts:

1. `git rm <missing-files>` to resolve the modify/delete conflicts.
2. Verify `.git/CHERRY_PICK_HEAD` still exists after the `git rm`.
3. Resolve any remaining content conflicts in other files.
4. Stage all resolved files.
5. `git cherry-pick --continue`.

Do not try to "revert" these files after resolution — they never existed on the target branch. The `git rm` is the resolution.

## Conflict-State Protection

If conflicts occur:

1. Verify `.git/CHERRY_PICK_HEAD` exists before doing anything else.
2. If missing, do not run `git cherry-pick --continue`.
3. Re-establish state: `git cherry-pick --abort`, then re-run from the start of apply.

**Why CHERRY_PICK_HEAD may be missing** (see also [../gotchas.md](../gotchas.md)): Some git versions drop it when all conflicts are modify/delete (no content conflicts remain). It can also disappear after an abort that wasn't followed by a fresh cherry-pick. If re-running reproduces the same modify/delete-only situation and CHERRY_PICK_HEAD is still missing, resolve with `git rm` + `git commit` (manually writing the cherry-pick message with the `-x` reference) rather than falling back to `git apply`.

**Never use `git checkout --theirs` or `git checkout --ours`** (see gotchas.md). Always resolve surgically by reading conflict markers.

## Escalation Ladder

When a cherry-pick hits conflicts, follow this order. Do not skip steps:

1. **Resolve in place** — resolve modify/delete conflicts with `git rm`, edit markers for content conflicts, then `git cherry-pick --continue`.
2. **Abort and re-run** — `git cherry-pick --abort`, then re-run `git cherry-pick -x <commit>`. Try a different resolution approach on the second attempt.
3. **Manual commit** — if CHERRY_PICK_HEAD is unrecoverable after re-run, resolve files manually, then `git commit` with a message that includes `(cherry picked from commit <sha>)`.
4. **`git apply --3way`** — last resort. Use when the cherry-pick is fundamentally incompatible with a clean cherry-pick flow (large exclusion sets, commit must be decomposed). Loses cherry-pick metadata and CHERRY_PICK_HEAD. Never use it for ≤5 excluded files when cherry-pick + `git rm` would work.

## When to Hand Off

Hand off to the adapt phase only when:
- a conflict requires code-level adaptation
- source intent must be inferred from surrounding code
- target-side APIs differ enough that a pure git resolution is insufficient

Remain in apply when the work is only:
- branch switching
- cherry-pick execution
- state verification
- staging resolved files
- continuing the in-progress cherry-pick

## Continue Rule

After conflicts are resolved:

1. Stage resolved files.
2. Verify `.git/CHERRY_PICK_HEAD` still exists.
3. Run `git cherry-pick --continue`.
4. Hand off to validation.
