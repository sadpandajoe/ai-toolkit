---
name: testing
description: "Use for creating, updating, or reviewing automated tests and test-plan adequacy. Do NOT use for manual QA execution, production debugging, or feature implementation beyond test harnesses."
---

# Testing

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for test-harness craft — writing, updating, and critiquing automated tests at the pytest/jest/vitest layer.

## Distinction vs QA

- **QA** = WHAT to test — scenarios, user-impact triage, fix validation, bug filing (`qa/` skill)
- **Testing** = HOW to test — writing test files, updating suites, reviewing test quality and test plans (this skill)

A QA scenario list feeds testing; testing implements the suite that protects those scenarios.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Create tests | First meaningful automated tests for an area without a suite | [references/create-tests.md](references/create-tests.md) |
| Update tests | Improve an existing suite — add, replace, remove | [references/update-tests.md](references/update-tests.md) |
| Review tests | Evaluate test quality, regression signal, production failure scenarios | [references/review-tests.md](references/review-tests.md) |
| Review test plan | Evaluate a plan's testing strategy — coverage approach, test layers, edge cases | [references/review-testplan.md](references/review-testplan.md) |

## Invocation Patterns

<!-- aitk-model-route:testing.test-authoring -->
- `create-tests` / `update-tests` — orchestrator spawns an `implementation` subagent with handoff back for `review-code`
- `review-tests` — reviewer subagent dispatched by `review-code` when tests exist in the diff
- `review-testplan` — reviewer subagent dispatched by `planning/references/iterate-review.md` when reviewing a plan's test strategy

## Notes

- `review-tests` vs `review-testplan` are mutually exclusive per `classify-diff` rules: if test files exist in the diff, use review-tests; otherwise review-testplan.
- `create-tests` and `update-tests` follow TDD when feasible — write failing test first, then implement.
