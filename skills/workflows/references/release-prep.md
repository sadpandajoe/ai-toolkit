# Release Prep

> **When**: You want to know whether a branch is ready to ship — clean
> working tree, build/artifacts succeed, CI is green.
> **Produces**: A `## Release Readiness` go/no-go report with the specific
> blockers, if any. Never publishes, tags, merges, or deploys.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `release-prep`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Usage

```
release-prep                  # Current branch
release-prep <branch>         # Named branch
```

## Routing

This entry exists so `release-prep` resolves as a canonical workflow name.
Route immediately to
[skills/goals/release-prep/SKILL.md](../../goals/release-prep/SKILL.md) for
the full check-branch/check-artifacts/check-ci/readiness flow, its gates,
and its checkpoint discipline — do not duplicate that skill's steps here.

## Notes

- Same command-name-registration pattern as `cherry-pick.md`/`refactor.md`/
  `watch-pr.md`: this file is a thin routing pointer, not a duplicate
  procedure. The full behavior lives in `skills/goals/release-prep/SKILL.md`.
- Publishing (tag/release/merge/deploy) is deliberately out of scope for
  both this file and the skill it routes to — see that skill's Notes for why
  a future publish step needs its own `external_effect`/`explicit`-mode
  contract rather than reusing this one.
