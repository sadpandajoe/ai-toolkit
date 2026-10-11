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

- **Scope.** With no arguments, the staged, unstaged, and untracked changes;
  a directory argument covers every file under it; `--files` names the files.
  Config and docs count when a repository check exercises them.
- **Command.** Run the repository's own targeted check for those files (its
  CI workflow, package scripts, task runner, or contributor guidance), with
  test workers capped per `rules/resource-management.md`. Run the full suite
  only when the user asks.
- **A check that did not run is not evidence.** A syntax-only check, or a
  command that failed to start, verifies nothing: name it and report `WEAK`.

## Report

```markdown
## Verification
Command: [the command that ran, or none]
Files changed: [N]
Tests found: [N]
Tests passed: [N] | Tests failed: [N]
Verification: STRONG / PARTIAL / WEAK — [reason]
```

Strength follows `rules/gates.md` (Verification Strength). A failing check is
never a strength: it is a `RETRY` (or `ESCALATE` by budget) for the caller,
reported with the failure output. This workflow is report-only; the caller
owns the response.
