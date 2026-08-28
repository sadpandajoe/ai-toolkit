# Refactor

> **When**: You want to restructure, simplify, or clean up code without
> changing its observable behavior.
> **Produces**: An invariants record, the refactored diff, an equivalence
> verification result, and a review outcome.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `refactor` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
refactor "extract the auth check into a shared helper"
refactor "simplify the retry logic in the ingest pipeline"
```

## Routing

This entry exists so `refactor` resolves as a canonical workflow name. Route
immediately to
[skills/goals/refactor/SKILL.md](../../goals/refactor/SKILL.md) for the full
classify/invariants/implement/verify/review flow, its gates, and its
checkpoint discipline — do not duplicate that skill's steps here.

## Notes

- Same command-name-registration pattern as `cherry-pick.md`: this file is a
  thin routing pointer, not a duplicate procedure. The full behavior lives in
  `skills/goals/refactor/SKILL.md`.
