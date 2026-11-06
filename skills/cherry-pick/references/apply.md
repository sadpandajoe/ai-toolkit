# Apply and Adapt

## Pick

Get the source commit's parent count from the pre-flight row
(`<skill-dir>/scripts/batch-preflight.sh <target-branch> <commit>` for a single
pick). One parent: `git cherry-pick -x <commit>`. A merge commit takes `-m 1`
only when parent 1 is the target-base side; otherwise stop as `Blocked: merge
parent ambiguous`.

Excluded files that exist on both branches are reverted after the pick;
excluded files missing on the target arrive as modify/delete conflicts.

## Modify/delete conflicts

`git rm <missing-files>` is the resolution, not a revert. Resolve other
conflicts, stage them, then `git cherry-pick --continue`. Before any
`--continue`, `.git/CHERRY_PICK_HEAD` must exist; if it is gone, `git
cherry-pick --abort` and re-run the pick ([gotchas.md](../gotchas.md) #2).

## Escalation ladder

In order; don't skip a step:

1. Resolve in place (`git rm`, edit markers), `git cherry-pick --continue`.
2. `git cherry-pick --abort`, then `git cherry-pick -x <commit>` with a
   different resolution.
3. CHERRY_PICK_HEAD unrecoverable: resolve the files, `git commit -C <sha>`
   (keeps author and message), then amend in the `(cherry picked from commit
   <sha>)` line.
4. Last resort, only when cherry-pick plus `git rm` cannot express the subset:
   `git diff <commit>^..<commit> -- <files> | git apply --3way`. It loses the
   author and the `-x` trailer ([gotchas.md](../gotchas.md) #6).

Partial picks still go through `git cherry-pick -x`; never prescribe
`git apply` or `format-patch | git apply` to a worker for them.

## Adapting conflicts

- Adapt to the target's APIs rather than pulling in structural changes; take
  only the functional part of a mixed commit.
- Never resolve with `--theirs`/`--ours` wholesale. Taking the source side of a
  conflicting region brings in whatever neighbouring source commits changed
  there. After resolving each file, compare against `git diff
  <commit>^..<commit> -- <file>`: lines that are neither in that diff nor
  already on the target are leaks; strip them.
- A required prerequisite is a stop, never silently pulled in. Reject when
  preserving intent needs a broad refactor.
- Ask the user when two behavior-preserving readings exist, the adaptation
  changes visible behavior, or a bundled PR has sub-fixes that look unrelated
  (list them with a reason each; the user usually wants the whole PR).
- A dropped or trimmed bug fix can leave the bug live on the target through
  another path; that goes in the report's next steps
  ([gotchas.md](../gotchas.md) #3).
