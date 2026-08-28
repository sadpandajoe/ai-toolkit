# Cherry-Pick / Backport

> **When**: Apply a commit or PR onto another branch, or run a release audit
> for backport candidates.
> **Produces**: Per-change `Applied`/`Partial`/`Blocked`/`Rejected`/`Skipped`
> classification, validation status, and push status.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `cherry-pick` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
cherry-pick <pr-url>                          # From a PR
cherry-pick <sha>                             # Single commit
cherry-pick <sha> --target <branch>           # Specific target branch
cherry-pick <sha> --force                     # Override reject-category gate
cherry-pick <sha-1> <sha-2> <sha-3>           # Batch
cherry-pick <sha-1> <sha-2> --plan-only       # Plan without applying
cherry-pick <sha-1> <sha-2> --no-push         # Validate locally; stop with push recommendation
```

## Authorization Boundary

Authorization mode: `invocation`. Per-cherry push is the default action once
validation passes — invoking `cherry-pick` is itself the authorization,
subject to the per-cherry push confirmation block. `--no-push` opts out:
validate locally and record `pending-authorization` instead of pushing. The
confirmation block still runs on every cherry regardless of `--no-push`.

## Routing

This entry exists for literal `cherry-pick`-command-name compatibility. Route
immediately to
[skills/goals/cherry-pick/SKILL.md](../../goals/cherry-pick/SKILL.md) for the
full investigate/gate/plan/apply/adapt/validate/push flow, its gates, and its
checkpoint discipline — do not duplicate that skill's steps here.

## Notes

- This file is a legacy command-name compatibility shim, same pattern as
  `fix-bug.md` and `test-pr.md` — deleted in Wave D once
  `interfaces/workflows.json`'s literal command-name layer is removed.
- `skills/goals/cherry-pick/SKILL.md` does not own `PROJECT.md`
  ("PROJECT.md is updated by the parent workflow, not this skill" — its own
  Notes section); when `cherry-pick` runs as this top-level command rather
  than as a step inside another goal skill, this shim's checkpoint is the
  parent, and it is the one that owns the `PROJECT.md` write.
