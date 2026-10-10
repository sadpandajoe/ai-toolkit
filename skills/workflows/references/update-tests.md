# Improve an Existing Test Suite


> **When**: You want to improve an existing test suite in a specific area, path, or function and have the workflow analyze gaps, update tests, verify, and review.
> **Produces**: Scoped test updates, verification results, remaining follow-up gaps, and either an authorized `test:` commit or a clear handoff.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `update-tests` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage
```
update-tests sql-lab
update-tests src/features/sql-lab
update-tests tests/unit/sql_lab/
update-tests --function normalize_query
update-tests <target> --no-pr        # Commit and push only; skip the draft PR
```

## Goal

Make the smallest high-signal improvement to the existing suite for the target
(a product area such as `sql-lab`, a code path, a test file or directory, or
`--function <name>`) and deliver it as a reviewed `test:` commit.
`update-tests` is the public workflow for existing-suite maintenance;
`review-code` runs inside it rather than as the user's next step. Prefer
replacing low-signal tests over adding redundant ones, size additions like the
neighboring test files, and keep scratch checks out of the commit. Write the
failing test first when feasible; when that is blocked, record why before
changing the suite. Only the main thread writes PROJECT.md; subagents return
compact handoffs.

Resolve the target from matching product-area names, code paths, and test
paths. If more than one plausible target remains, stop and name them: the
choice is the user's.

When the target has no meaningful suite, say so and continue as `create-tests`
(carrying `--no-pr`): the deliverable is the same, and a first suite follows
`create-tests`' procedure, not this improvement loop. With `--step` (or
`--no-handoff`), stop and recommend `create-tests` instead.

Find weak or low-signal tests, missing behavioral coverage, production blind
spots, and simplification opportunities with
[skills/testing/references/review-tests.md](../../testing/references/review-tests.md);
for workflow-heavy, integration-heavy, or user-visible targets, add a compact
QA must-cover scenario matrix. Sort the results into must-update now, suggested
follow-up, and out of scope, and change only the must-update set with
[skills/testing/references/update-tests.md](../../testing/references/update-tests.md),
which owns updating, adding, and replacing tests and the targeted
verification.

## Exit Criteria

- Verification is strong (`verify` or an equivalent targeted check), and
  `review-code` has run on the changed repo-tracked files: one independent
  review, fix the accepted findings, one delta pass over the fix. A finding
  still open after the delta is `ESCALATE` (or `USER_DECISION` when it needs a
  product call), not a third round.
- If verification is strong and `review-code` leaves no unresolved `[major]` or `[minor]` issues:
  - create a `test:` commit and push (when the branch already has an upstream, require `git rev-parse --abbrev-ref "<branch>@{upstream}"` to equal `<remote>/<branch>`, else pause as an ambiguous push target, then push with `git push "<remote>" "HEAD:refs/heads/<branch>"`, never a bare `git push`, never `-u`; with no upstream, `git push -u <remote> HEAD`, where `<remote>` is `branch.<name>.pushRemote`, else `remote.pushDefault`, else `origin`, pausing on an ambiguous push target), then open a draft PR with `create-pr --draft` straight through, with no checkpoint reservation (no confirmation, never from `main`); `--no-pr` stops after the push and records `pushed — awaiting PR request`; promotion to ready, reviewers, and merge need the user's words

  Commit message format:
  - `test: update <scope> coverage`
  - fallback: `test: update targeted coverage`

  Stop instead of committing when verification is partial or blocked,
  meaningful ambiguity remains, or the run continued as `create-tests`.
- PROJECT.md has a `## Tests Updated` entry before the chat summary, so a
  fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md)
  after `update-tests` keeps the record:

  ```markdown
  ## Tests Updated
  Files: [list]
  Change: [one-liner — what behavior changed or got covered]
  Verification: [strength label]
  Commit: [SHA or "no commit"]
  ```

  When a later phase runs in a fresh worker, persist what it needs first:
  `## Test Suite Analysis` (target, weak tests, missing coverage, planned
  updates) before the update, `## Test Updates Applied` (files changed; tests
  added, updated, or replaced) before review, and `## Test Review Status`
  (verification result, review gate status) after it. The worker and any
  later session resume only from PROJECT.md.

## Summary

```markdown
## Update-Tests Complete

### Outcome
- [Updated suite / handed off to create-tests / stopped on blocker]

### Scope
- [Target area, path, or function]

### Suite Outcome
- [Updated existing suite / handed off to create-tests]

### Behavioral Coverage
- [What regressions or behaviors are now covered]

### Review / Quality
- [Review rounds and final review outcome]

### Verification
- [Checks run]

### Risks / Blockers
- [Anything still weak, blocked, or intentionally left for follow-up]

### Remaining Gaps
- [Suggested follow-up tests or none]

### Commit Result
- [Created `test:` commit / no commit and why]
```
