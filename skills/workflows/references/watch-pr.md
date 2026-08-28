# Watch PR

> **When**: You want a PR babysat unattended across multiple iterations —
> CI checked, comments checked, deltas routed, until stable or escalated.
> **Produces**: A `WATCH.md` iteration log, ledgers of reruns/comments/fix
> attempts, and a terminal `stable`/`escalated`/`blocked` status.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `watch-pr` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
watch-pr <pr-number|pr-url>
```

## Authorization Boundary

Authorization mode: `invocation`. Invoking `watch-pr` grants standing
authorization for fast-forward commits to the PR branch and factual
replies/resolution within the routed scope — see
[skills/pr-watch/SKILL.md](../../pr-watch/SKILL.md)'s Authorization Boundary
for the exact grant and its limits (no amend/rebase/force-push/merge/approve).

## Routing

This entry exists so `watch-pr` resolves as a canonical workflow name. Route
immediately to
[skills/goals/watch-pr/SKILL.md](../../goals/watch-pr/SKILL.md) for the full
prepare/iterate/stop/report flow, its gates, and its checkpoint discipline —
do not duplicate that skill's steps here.

## Notes

- Same command-name-registration pattern as `cherry-pick.md`/`refactor.md`:
  this file is a thin routing pointer, not a duplicate procedure. The full
  behavior lives in `skills/goals/watch-pr/SKILL.md`, which delegates its
  iteration/routing/stop contract to `skills/pr-watch/SKILL.md`.
