# Implementation

## Golden Rules

- Implement the accepted artifact (plan slice, RCA, or approved comment), not a
  wider idea of it. Out-of-scope needs go in the handoff as residual risk.
- Regression evidence first: bugs get a RED/GREEN test, features get the
  slice's acceptance tests as the spec. If a test cannot run here, write it and
  record the gap; never silently switch to test-after.
- Update existing code before creating new; smallest change that meets the exit
  criteria.
- **Fix the invariant, not the test.** When a test is red, or proposed for
  deletion to fit broken-but-current behavior, fix the behavior. Loosen or
  delete a test only when the test itself is wrong: it asserts an unintended
  side effect, depends on a removed feature, or encodes a judgment nobody
  stands by.
- **Escalate test strategy only when it is ambiguous.** Routine test authoring
  is the implementer's or tester's job; a specialist answers "does this test
  prove the right thing?", not "write the tests".
- Stage explicit paths, never `git add -A` or `git add .`: those stage
  `PROJECT.md`, `PLAN.md`, and unrelated work. `--no-verify` is hook-blocked.
  Amend, rebase, and force-push need explicit authorization; commit, push, and
  PR policy is in `rules/universal.md`.

## Test-First Modes

**RED/GREEN per slice (bugs).** Write the failing regression test, run it and
see it fail, make the minimum change, run it and see it pass. A test that passes
before the fix does not capture the bug.

**Test set as specification (features).** Write the slice's acceptance tests
first as the spec, implement, then reconcile: fix the code when the code is
wrong, fix the test and note why when the spec evolved.

## Pointers

- Worker scope and handoff: `skills/implement-change/SKILL.md`.
- Checks before a commit: the repository's build, typecheck, lint, formatter
  in check mode, tests for the changed files, and its pre-commit hooks, run
  through `skills/verification-loop/SKILL.md`; a worktree needs its
  dependencies installed first (`rules/resource-management.md`).
