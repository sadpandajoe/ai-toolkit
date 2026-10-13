# Create the First Meaningful Tests


> **When**: You want standalone test-only work for an area that does not yet have a meaningful suite, or `update-tests` has handed off because there is nothing real to update.
> **Produces**: A first meaningful test suite or net-new high-signal coverage, validation results, and a summary of remaining gaps.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

`create-tests` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`.

## Usage
```
create-tests                         # First meaningful tests for current uncommitted work
create-tests <file>                  # First meaningful tests for a specific file
create-tests --function <name>       # First meaningful tests for a specific function
create-tests <target> --no-pr        # Commit and push only; skip the draft PR
```

## Goal

Give an area that has no meaningful suite its first high-signal tests (the
uncommitted changes, a file, or `--function <name>`) and deliver them as a
reviewed `test:` commit. This is test-only work, not the entry point for
feature or bug work, and `review-code` runs inside it rather than as the
user's next step. Prefer the smallest set of tests that locks in real
behavior: size them like the neighboring test files, roughly one focused test
per behavior, and keep scratch checks out of the commit.

Write the tests with
[skills/testing/references/create-tests.md](../../testing/references/create-tests.md),
which owns choosing the behaviors to cover, the test layer, and the
targeted verification. Only the main thread writes PROJECT.md; subagents
return compact handoffs.

## Exit Criteria

- Verification of the new tests is strong (`verify` or an equivalent targeted
  check), and `review-code` has run on the changed repo-tracked files: one
  independent review, fix the accepted findings, one delta pass over the fix.
  A finding still open after the delta is `ESCALATE` (or `USER_DECISION` when
  it needs a product call), not a third round.
- With strong verification and a passing `review-code`, deliver the tests as
  a `test:` commit without asking: draft the title and body with `create-pr`
  steps 2-5, then run `bin/aitk deliver --workflow create-tests --title
  "<title>" --body-file <file> --message "test: <scope>" [--no-pr]` and paste
  the block it prints. It refuses below a recorded `STRONG` run or without the
  review record, and never delivers from the default branch. Promoting the
  draft, reviewers, and merge need the user's words.
- PROJECT.md has a `## Tests Created` entry before the chat summary, so a
  fresh session or [`archive-project-file`](../../archive-project-file/SKILL.md)
  after `create-tests` keeps the record:

  ```markdown
  ## Tests Created
  Files: [list]
  Behaviors covered: [one-liner]
  Test layer: [chosen layer]
  Verification: [strength label]
  ```

  When verification or review runs in a fresh worker, write this entry before
  that phase starts and add `## Test Review Status` (verification result,
  review gate status) after it: the worker and any later session resume only
  from PROJECT.md.

## Summary

```markdown
## Create-Tests Complete

### Outcome
- [Created first meaningful suite / stopped on blocker]

### Scope
- [What behavior or files were covered]

### Behavioral Coverage
- [What regressions or behaviors are now covered]

### Review / Quality
- [Review rounds and final review outcome]

### Verification
- [Checks run]

### Risks / Blockers
- [Anything still unverified or out of scope]

### Remaining Gaps
- [Anything still not covered]

### Next Decision
- [Committed and pushed / needs more work]
```
