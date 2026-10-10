# Review Tests

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Goal

Judge whether the tests around the current change give real regression
protection, and whether the change could still fail in production with every
test green. The independent reviewer applies this when a diff contains tests;
`create-tests` and `update-tests` use it to decide what to write or change.

Look at four things:

- **Behavioral coverage.** Which real behaviors, state transitions, and failure
  scenarios the tests exercise, and which the change introduces without a test.
  A missing test is a finding when you can name the assertion that fails on
  today's code and passes once the change is correct (`rules/code-review.md`).
- **Low-signal tests.** Tests that would pass with the code under test removed:
  tied to implementation details, mocking internal or fast deterministic code,
  asserting setup or mock pass-through, brittle for reasons unrelated to the
  behavior, or redundant with a neighbor. Say whether each should be
  strengthened, merged, moved to a lower layer, or removed.
- **Production blind spots.** Realistic failures the suite would not catch:
  races, unexpected input, partial failures, state inconsistencies, integration
  and timing problems.
- **Simplification.** Tests to remove, merge, or replace with fewer
  higher-signal ones.

Report what you find in the format of the contract you are running under; a
reviewer worker returns severity-tagged findings and puts recommended
additions in the summary.
