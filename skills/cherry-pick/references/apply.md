# Apply and Adapt

- **Merge commits.** The pre-flight row gives the parent count
  (`<skill-dir>/scripts/batch-preflight.sh <target-branch> <commit>` for a
  single pick). A merge takes `-m 1` only when parent 1 is the target-base
  side; otherwise stop as `Blocked: merge parent ambiguous`.
- **Excluded files.** Ones present on both branches are reverted after the
  pick. Ones missing on the target arrive as modify/delete conflicts, resolved
  with `git rm`, not a revert. `.git/CHERRY_PICK_HEAD` must exist before any
  `git cherry-pick --continue` ([gotchas.md](../gotchas.md) #2).
- **When a pick won't go through,** in this order:
  1. resolve in place and `--continue`;
  2. `--abort`, then `git cherry-pick -x <commit>` with a different resolution;
  3. `CHERRY_PICK_HEAD` unrecoverable: resolve, `git commit -C <sha>` (keeps
     author and message), then amend in `(cherry picked from commit <sha>)`;
  4. only when cherry-pick plus `git rm` cannot express the subset:
     `git diff <commit>^..<commit> -- <files> | git apply --3way`, which loses
     the author and the trailer ([gotchas.md](../gotchas.md) #6).

  Never prescribe `git apply` to a worker for a partial pick.
- **Adapting.** Adapt to the target's APIs rather than pulling in structure,
  and never resolve a whole file with `--theirs` or `--ours`
  ([gotchas.md](../gotchas.md) #1). A required prerequisite is a stop, never
  silently pulled in; reject when preserving intent needs a broad refactor.
  Ask before an adaptation that changes visible behavior. A bundled PR whose
  sub-fixes look unrelated goes to the user with a reason for each; the user
  usually wants the whole PR.
