# Implementation

## Golden Rules

- Implement the accepted artifact (plan slice, RCA, or approved comment), not a
  wider idea of it. Out-of-scope needs go in the handoff as residual risk.
- Regression evidence first: bugs get a RED/GREEN test, features get the
  slice's acceptance tests as the spec. If a test cannot run here, write it and
  record the gap; never silently switch to test-after.
- Update existing code before creating new; smallest change that meets the exit
  criteria.
- Commit only working states (verification and review passed), staging files
  by name, never with `git add -A` or `git add .`: those stage `PROJECT.md`,
  `PLAN.md`, and unrelated work. Committing and pushing the current feature branch
  needs no confirmation, and a workflow opens a draft PR after the push
  (`--no-pr` skips it); marking it ready for review waits for the user.
- Never rewrite history unless explicitly asked: no force push, no rebase of
  shared branches, no amending published commits; amend only HEAD.
- PR descriptions are factual: what changed and why.

## Test-First Modes

**RED/GREEN per slice (bugs).** Write the failing regression test, run it and
see it fail, make the minimum change, run it and see it pass. A test that passes
before the fix does not capture the bug.

**Test set as specification (features).** Write the slice's acceptance tests
first as the spec, implement, then reconcile: fix the code when the code is
wrong, fix the test and note why when the spec evolved.

## Worker Scope

A routed or native implementation worker receives one slice and returns the
handoff in `skills/implement-change/SKILL.md`. It never commits, never edits
`PROJECT.md` or `PLAN.md`, never widens scope, and stops with `blocked` after the
same approach fails twice. The parent runs acceptance, owns review, and owns
any authorized git action.

## Standards

Match the repository's conventions for function size, file size, and nesting.
Where it has none, prefer small focused units, early returns, descriptive
names, and explicit error handling.

## Pre-Flight Before Any Commit

Build, typecheck, lint, formatter in check mode, tests for changed files, and
pre-commit hooks (never `--no-verify`). In a worktree, install dependencies
first.
