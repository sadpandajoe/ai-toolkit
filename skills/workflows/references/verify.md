# Run Tests on Changed Files

> **When**: After implementation, before review, or standalone to check the current state.
> **Produces**: Verification report with test results and confidence level.

## Effect Boundary

Effect: `read_only`.

## Usage

```
verify
verify src/api/
verify --files auth.ts dashboard.ts
```

Without arguments, verifies all uncommitted changes.

## Goal

Report how strongly the current changes are verified; fix nothing. Callers
(`create-feature`, `fix-bug`, and the rest) branch on the strength, and a
standalone run only reports it.

- **Scope.** With no arguments, the staged, unstaged, and untracked changes
  (`git diff --name-only` plus untracked files); a directory argument covers
  every file under it; `--files` names the files. Keep any file a repository
  check exercises, including docs and config the repo tests.
- **Command.** Run the repository's own targeted check for those files, taken
  from its CI workflow, package scripts, Makefile or task runner, or
  contributor guidance (CONTRIBUTING, AGENTS.md, CLAUDE.md), and map changed
  files to tests by naming convention, test-directory layout, or imports.
  When several ecosystems are present, use the one matching the changed
  files. Set test worker counts per `skills/testing/rules.md`. Scope tests to
  the changed files; run the full suite only when the user asks.
- **A check that did not run is not evidence.** A syntax-only check, or a
  command that failed to start, verifies nothing: name the check that did not
  run and why, and report `WEAK`.

## Report

```markdown
## Verification
Command: [the command that ran, or none]
Files changed: [N]
Tests found: [N]
Tests passed: [N] | Tests failed: [N]
Verification: STRONG / PARTIAL / WEAK — [reason]
```

Strength follows `rules/gates.md` (Verification Strength):
- **STRONG**: the failing or acceptance command itself (or a close equivalent)
  ran locally and passes
- **PARTIAL**: related checks that exercise the changed code ran and pass, but
  not the exact command
- **WEAK**: inspection only — no tests found or tests could not run

A failing check is never a strength: it is a `RETRY` (or `ESCALATE` by budget)
for the caller, reported with the failure output. File-to-test coverage is
reported as `Files changed / Tests found` above and does not raise the tier.
This workflow is report-only; the caller owns the response.
