# Tests

> **When**: Test-only work: the first meaningful tests for an area without a real suite, or a high-signal improvement to an existing suite.
> **Produces**: Reviewed, verified test changes delivered as a `test:` commit and draft PR, a `## Tests` entry in `PROJECT.md`, and the gaps that remain.

## Effect Boundary

Effect: `git_mutation`.

## Usage

```
tests sql-lab                   # area, path, test file or directory
tests --function normalize_query
tests                           # the current uncommitted work
tests <target> --no-pr          # commit and push only; skip the draft PR
tests <target> --step           # stop at the mode switch instead of continuing
```

## Mode

Resolve the target from product-area names, code paths and test paths; when
more than one plausible target remains, name them and let the user choose.

- **Update** when the target has a real suite: make the smallest useful
  improvement. Find low-signal tests (they pass with the code removed),
  missing behavioral coverage, production blind spots, and tests to merge;
  for workflow-heavy or user-visible targets add a compact QA must-cover
  matrix. Sort the results into must-update now, suggested follow-up, and out
  of scope, and change only the must-update set. Update existing tests before
  adding new ones, and replace a low-signal test only with a clearly stronger
  one rather than adding beside it.
- **First suite** when there is no real suite: say so and switch (with
  `--step`, stop and ask instead). List the behaviors, state transitions and
  failure scenarios the area has without a test, and cover each at the
  narrowest layer that proves it; size the set like the neighboring test
  files, roughly one focused test per behavior.

Either mode writes the failing test first when feasible, and records why when
it is blocked. For a substantial suite, dispatch the tester through the
`testing.test-authoring` boundary in `skills/testing/SKILL.md`; otherwise work
inline. Either way the result is the tester handoff (`## Handoff: tester`).
Keep scratch checks out of the commit. Only the main thread writes
`PROJECT.md`; workers return handoffs.

## Review and Delivery

Verify the changed tests with `bin/aitk verify --run "<cmd>"`, then run
`review-code` on the changed files: one independent review, fix the accepted
findings, one delta pass over the fix. A finding still open after the delta is
`ESCALATE` (or `USER_DECISION` when it needs a product call), never a third
round. Stop before committing when verification is partial or blocked or real
ambiguity remains.

With `STRONG` verification and review `PASS`, deliver without asking: draft
the title and body with `create-pr` steps 2-5, then run `bin/aitk deliver
--workflow tests --title "<title>" --body-file <file> --message "test: <scope>
coverage" [--no-pr]` and paste the block it prints. It refuses without the
recorded run and review and never delivers from the default branch. Promoting
the draft, reviewers, and merge need the user's words.

## Record and Summary

Before the chat summary, append to `PROJECT.md` (and, when a phase runs in a
fresh worker, write the entry before that phase so the worker and any later
session resume from it):

```markdown
## Tests
Mode: <first suite | update>
Files: <list>
Behaviors covered: <one line>
Verification: <strength label>
Review: <gate>
Commit: <SHA or "no commit">
```

Summarize as `## Tests Complete`: outcome and mode, scope, behaviors now
covered, review rounds and verdict, checks run, risks or blockers, and the
remaining gaps.
