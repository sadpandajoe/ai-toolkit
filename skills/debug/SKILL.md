---
name: debug
description: Investigating a bug or failure — find the root cause, recover Git state, classify a CI failure, review an RCA, search for an existing upstream fix, or verify a CI fix landed. Do NOT use for implementing the fix (use implement-change/), writing tests (use testing/), or turning a loose bug report into a repro plan before investigating (use qa/).
---

# Debug

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for all diagnostic work — finding root causes, validating them, and confirming fixes. References have distinct shapes (investigation / classifier / reviewer / search workflow / verification) unified by the common goal of *understanding what broke*.

## Phases

| Phase | When | Shape | Reference |
|-------|------|-------|-----------|
| Investigate change | Open-ended investigation — bug or RCA | Orchestrator inline OR subagent | [references/investigate-change.md](references/investigate-change.md) |
| Recover Git state | A failed Git operation or mistaken mutation needs bounded recovery | Orchestrator inline | [references/recover-git-state.md](references/recover-git-state.md) |
| Gather CI logs | Resolve actual failing logs from GitHub, local files, or artifacts | Orchestrator inline | [references/ci-gather-logs.md](references/ci-gather-logs.md) |
| Classify CI failure | CI log / artifact available, need pattern match | Fast pattern-match producer | [references/ci-classify-failure.md](references/ci-classify-failure.md) |
| Orchestrate CI fix | Group failures, route complexity, apply safe fix strategy | Orchestrator inline | [references/ci-fix-orchestration.md](references/ci-fix-orchestration.md) |
| Review RCA | RCA produced, needs critique before implementation | Reviewer subagent prompt | [references/review-rca.md](references/review-rca.md) |
| Check existing fix | Is this bug already fixed upstream or pending in a PR? | Parallel git+gh search | [references/check-existing-fix.md](references/check-existing-fix.md) |
| Verify CI fix | CI fix applied, determine STRONG/PARTIAL/WEAK locally | Verification strength tiering | [references/ci-verify-fix.md](references/ci-verify-fix.md) |

## Typical Composition

**Bug workflow** (`fix-bug`):
1. `check-existing-fix` → is fix already upstream?
2. `investigate-change` (with "Investigating a Bug" section) → produces RCA
3. `review-rca` → critiques the RCA
4. The workflow routes implementation, review, QA, and reporting to their own skills.

**CI workflow** (`fix-ci`):
1. `ci-gather-logs` → resolve real failing logs or artifact chunks
2. `ci-classify-failure` → pattern-match or novel
3. `ci-fix-orchestration` → group failures, route gates, choose safe fix strategy
4. `ci-verify-fix` → STRONG/PARTIAL/WEAK tier

**Cherry-pick**:
1. `check-existing-fix` → is the cherry still needed?

## Shape Notes

References here are intentionally diverse:
- `investigate-change` is an open investigation flow (the orchestrator reads the reference and follows steps).
- `recover-git-state` is a safety ladder for inspecting damage, preserving a rollback point, and escalating only with explicit authorization.
- `ci-gather-logs` is a retrieval and manifest setup flow.
- `ci-classify-failure` is a pattern-match producer (returns a classified failure block).
- `ci-fix-orchestration` is a workflow-owned routing reference; it does not edit files by itself.
- `review-rca` is a reviewer subagent prompt (spawned with its content as prompt).
- `check-existing-fix` is a parallel-search workflow (runs git+gh queries in parallel).
- `ci-verify-fix` is a verification-strength tiering reference (definitions + stop conditions).

The umbrella unifies them by workflow domain (diagnosis), not by shape.

## Notes

- `investigate-change` has a "When Investigating a Bug" section with bug-specific framing fields — use it for `fix-bug`.
- `review-rca` is a *critic* — it scores and returns findings, unlike investigate-change which *produces* the RCA.
- `check-existing-fix` can be skipped when the change is a dependency upgrade or structural refactor (not an isolated defect correction).
- End-to-end sequencing belongs in the selected canonical workflow reference.
  This skill owns diagnostic phases only; the workflow routes implementation,
  review, QA, and reporting to their domain skills.
