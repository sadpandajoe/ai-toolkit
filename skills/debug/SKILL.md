---
name: debug
description: Investigating a bug or failure — find the root cause with evidence, grade it at the RCA gate, escalate uncertain RCA to an independent specialist, recover Git state, classify a CI failure, search for an existing upstream fix, or verify a CI fix landed. Do NOT use for implementing the fix (use implement-change/), writing tests (use testing/), or turning a loose bug report into a repro plan before investigating (use qa/).
---

# Debug

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for diagnostic work: finding root causes, evidencing them, and
confirming fixes. Evidence-first: confidence is a number with a reason, and the
RCA gate passes on evidenced mechanism, not on a plausible story.

## Phases

| Phase | When | Shape | Reference |
|---|---|---|---|
| Investigate change | Open-ended investigation of a bug or regression | Parent inline, or the debugger worker when logs are noisy | [references/investigate-change.md](references/investigate-change.md) |
| RCA gate | Investigation produced a hypothesis | Parent grades STANDARD; specialist grades COMPLEX or uncertain | [references/review-rca.md](references/review-rca.md) |
| Check existing fix | Is this already fixed upstream or pending in a PR? | Parallel git and gh search | [references/check-existing-fix.md](references/check-existing-fix.md) |
| Recover Git state | A failed Git operation needs bounded recovery | Parent inline | [references/recover-git-state.md](references/recover-git-state.md) |
| Gather CI logs | Resolve the real failing logs or artifacts | Parent inline | [references/ci-gather-logs.md](references/ci-gather-logs.md) |
| Classify CI failure | Logs available, need pattern match | Producer | [references/ci-classify-failure.md](references/ci-classify-failure.md) |
| Orchestrate CI fix | Group failures, route, choose safe fix | Parent inline | [references/ci-fix-orchestration.md](references/ci-fix-orchestration.md) |
| Verify CI fix | Fix applied; determine local verification strength | Tiering | [references/ci-verify-fix.md](references/ci-verify-fix.md) |

## Composition

- **fix-bug**: check-existing-fix → investigate-change → RCA gate → the
  workflow plans, implements, verifies, and reviews.
- **fix-ci**: ci-gather-logs → ci-classify-failure → ci-fix-orchestration →
  ci-verify-fix. The specialist enters only for CI-only failures, flakiness or
  races, or repeated unexplained failures.
- **RCA only** ("investigate why X happens, do not change code"): investigate
  → RCA gate → an evidence-backed RCA artifact in `PROJECT.md` another workflow
  can consume.
- **cherry-pick**: check-existing-fix decides whether the cherry is needed.

## Notes

- Scope git history searches to the main branch and the current branch; never
  `--all`.
- Separate the incident root cause from latent bugs found along the way; keep
  the distinction in `PROJECT.md` and the later PR description.
- `check-existing-fix` can be skipped for dependency upgrades and structural
  refactors.
