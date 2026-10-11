# Recover Git State

Use only after a Git operation has gone wrong. Recovery does not broaden
authorization.

1. Make a rollback point first: a rescue branch, or a stash that includes the
   needed untracked files (`git stash -u`), checked with `git status`.
2. Use the operation-specific `--abort` (merge, rebase, cherry-pick, revert)
   before any reset.
3. Before `git reset --hard` or `git clean`, have an exact target, a dry run
   (`git clean -nd`), and the user's confirmation.
4. Stop when the known-good state is uncertain.
