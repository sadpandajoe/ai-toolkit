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

The `tests` workflow (`skills/workflows/references/tests.md`) owns both modes,
a first suite and an update to an existing one. The independent reviewer
grades tests in a diff by `rules/code-review.md`, and the plan validator grades
a plan's test strategy by its own contract.

## Invocation

<!-- aitk-model-route:testing.test-authoring -->
Launch one fresh tester worker on `implementation` (the toolkit's tester agent)
for a substantial suite in `tests`; it returns the `## Handoff: tester` block.
The parent implements small test changes inline and hands either result to
`review-code`.
