---
name: debug
description: Investigating a bug or failure — find the root cause with evidence, grade it at the RCA gate, escalate uncertain RCA to an independent specialist, recover Git state, classify a CI failure, search for an existing upstream fix, or verify a CI fix landed. Do NOT use for implementing the fix (use implement-change/), writing tests (use testing/), or turning a loose bug report into a repro plan before investigating (use qa/).
---

# Debug

Umbrella for diagnostic work: finding root causes, evidencing them, and
confirming fixes. The RCA gate passes on an evidenced mechanism, not on a
plausible story. Before diagnosing a flake or an API-boundary bug, read
[gotchas.md](gotchas.md) and [lessons.md](lessons.md).

## Phases

| Phase | When | Shape | Reference |
|---|---|---|---|
| Investigate change | Open-ended investigation of a bug or regression | Parent inline, or the debugger worker when logs are noisy | [references/investigate-change.md](references/investigate-change.md) |
| RCA gate | Investigation produced a hypothesis | Parent grades STANDARD; specialist grades COMPLEX or uncertain | [references/review-rca.md](references/review-rca.md) |
| Check existing fix | Is this already fixed upstream or pending in a PR? | Parallel git and gh search | [references/check-existing-fix.md](references/check-existing-fix.md) |
| Recover Git state | A failed Git operation needs bounded recovery | Parent inline | [references/recover-git-state.md](references/recover-git-state.md) |
| Gather CI logs | Resolve the real failing logs or artifacts | Parent inline | [references/ci-gather-logs.md](references/ci-gather-logs.md) |
| Classify CI failure | Logs available, need pattern match | Producer | [references/ci-classify-failure.md](references/ci-classify-failure.md) |
| Orchestrate CI fix | Group failures, choose the fix path | Parent inline | [references/ci-fix-orchestration.md](references/ci-fix-orchestration.md) |

Verifying a CI fix follows `fix-ci` step 6 and the strength table in
`rules/gates.md`.

## Composition

`fix-bug` and `fix-ci` own the end-to-end order; `cherry-pick` uses
check-existing-fix to decide whether a pick is needed. RCA-only work
("investigate why X happens, do not change code") stops after the RCA gate
and writes a `PROJECT.md` artifact only when the user asks for one.

## Notes

- Scope git history searches to the main branch, the current branch and
  merged PRs; never `git log --all`, because unmerged branches hold
  experimental code that never shipped.
- Separate the incident root cause from latent bugs found along the way; keep
  the split in `PROJECT.md` and the later PR description as **Incident Root
  Cause**, then **Latent Bugs / Hardening** when present.
