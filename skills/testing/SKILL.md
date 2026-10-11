---
name: testing
description: "Use for creating, updating, or reviewing automated tests and test-plan adequacy. Do NOT use for manual QA execution, production debugging, or feature implementation beyond test harnesses."
---

# Testing

Umbrella for test-harness craft: writing and updating automated tests. Test-first
modes and "fix the invariant, not the test" live in `rules/implementation.md`
(Test-First Modes); test-worker caps live in `rules/resource-management.md`.

## Distinction vs QA

QA is what to test (scenarios, triage, validation, bug filing); testing is how
(test files, suites, test quality).

## Phases

| Phase | When | Reference |
|---|---|---|
| Create tests | First meaningful tests for an area without a suite | [references/create-tests.md](references/create-tests.md) |
| Update tests | Improve an existing suite | [references/update-tests.md](references/update-tests.md) |

The independent reviewer grades tests in a diff by `rules/code-review.md`, and
the plan validator grades a plan's test strategy by its own contract.

## Invocation

<!-- aitk-model-route:testing.test-authoring -->
Launch one fresh tester worker on `implementation` (the toolkit's tester agent)
for a substantial suite in `create-tests` / `update-tests`; the parent
implements small test changes inline and hands either result to `review-code`.
