---
name: testing
description: "Use for creating, updating, or reviewing automated tests and test-plan adequacy. Do NOT use for manual QA execution, production debugging, or feature implementation beyond test harnesses."
---

# Testing

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.
Read and apply `rules/testing.md`.

Umbrella for test-harness craft: writing, updating, and critiquing automated
tests. The parent or the toolkit's tester agent owns normal test work; a
specialist enters only for the hard question "does this test prove the right
thing?".

## Distinction vs QA

QA is what to test (scenarios, triage, validation, bug filing); testing is how
(test files, suites, test quality).

## Phases

| Phase | When | Reference |
|---|---|---|
| Create tests | First meaningful tests for an area without a suite | [references/create-tests.md](references/create-tests.md) |
| Update tests | Improve an existing suite | [references/update-tests.md](references/update-tests.md) |
| Review tests | Evaluate test quality and regression signal | [references/review-tests.md](references/review-tests.md) |
| Review test plan | Evaluate a plan's testing strategy | [references/review-testplan.md](references/review-testplan.md) |

## Invocation

<!-- aitk-model-route:testing.test-authoring -->
Launch one fresh tester worker on `implementation` (the toolkit's tester agent)
for a substantial suite in `create-tests` / `update-tests`; the parent
implements small test changes inline and hands either result to `review-code`.
- `review-tests` is inlined in the independent reviewer's contract
  (`agents/specialists/reviewer.md`) and `review-testplan` in the plan
  validator's (`agents/specialists/plan-validator.md`); they are mutually
  exclusive per artifact (a diff that contains tests versus a plan's test
  strategy).

## Notes

Tests prove the signal: a new test must be shown to fail when the behavior
breaks. Test-first when feasible; when blocked, write the test and record the
gap.
