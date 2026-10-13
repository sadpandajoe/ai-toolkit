# CI Fix Orchestration

Use after failures are classified. `fix-ci` owns the order, the triage
routing (step 1) and the commit action (step 8); this reference covers
grouping and the amend mechanics.

## Group Before Fixing

The main thread groups classified failures by root cause and owns the order;
classification records go to `CI_FIX.md` when the run has one.

- **One shared root cause** → one fix path.
- **Independent root causes** → fix in waves, smallest and safest first.
- **Pre-existing or flaky** → excluded from the fix path, with evidence. All
  pre-existing → exit early with evidence and no fix or review cycle.

Keep each fix on the failing surface; when verification is weak or the root
cause is ambiguous, stop instead of widening scope.

## Amend Targets

An amend needs the user's explicit authorization (`fix-ci` step 8). On a
cherry-pick branch (`git log --grep="cherry picked from commit"` on recent
commits), the amend target is the cherry-picked commit that last touched the
failing files (`git log -- <file>` filtered to those SHAs), not necessarily the
latest. For a non-tip commit:

```bash
git commit --fixup=<originating-sha>
git rebase --autosquash <base>
```

Pre-commit trap: staging commit A's fixup makes hooks stash the unstaged
changes (including commit B's fix) and check the incomplete state, so commit
fixups in dependency order.
