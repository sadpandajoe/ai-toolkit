---
tier: Standard
---

# PR Review Batch

Use when `review-pr` receives multiple PR numbers or `--all-open`.

## Batch Contract

The main thread is a thin orchestrator:
- resolve the PR list
- dispatch bounded single-PR reviews
- collect compact results
- post aggregate summary

The main thread must not accumulate full diffs or full review transcripts for every PR.

## Resolve PRs

- `--all-open`: run `gh pr list --json number,title --state open`
- Multiple numbers: parse provided refs

## Dispatch

<!-- aitk-model-route:review.pr-batch -->
For each PR, dispatch a subagent on `review`/`deep-review` with:
- PR number/ref
- flags (draft/summary by default; pass `--auto` only when the user explicitly requested auto-posting)
- pointer to [pr-review.md](pr-review.md)
- pointer to [pr-posting.md](pr-posting.md)
- compact return contract

Return contract:

```markdown
PR:
Title:
Recommendation: approve | request-changes | comment
Posted: yes | no | draft
Top finding:
Finding counts:
Residual risk:
```

Batch mode runs the **findings** lenses only — the Code-judo generative pass is
disabled here. Its unscored restructuring *proposals* have no slot in the compact
per-PR return contract above, and the `deep-review` route is too expensive to fan
out across a batch. When a specific PR warrants a Code-judo pass, run a single-PR
deep review ([review-pr](../../workflows/references/review-pr.md)) instead.

Concurrency: run up to 3-5 PR reviews in parallel. Lower concurrency if PRs are unusually large, share code ownership, or the repo is resource constrained.

## Per-Wave PROJECT.md Persistence (Hard Gate Before Clear)

After each wave of ≤3 PRs completes, before launching the next wave, append a `## Review-PR Batch Wave N` block to PROJECT.md:

```markdown
## Review-PR Batch Wave N
PRs: [#101, #102, #103]
| PR | Recommendation | Posted | Top Finding | Residual Risk |
|----|----------------|--------|-------------|---------------|
| #101 | approve | draft | none | none |
| #102 | request-changes | no | [...] | [...] |
| #103 | comment | yes | [...] | [...] |
Next wave: [PR numbers OR "aggregate"]
```

For batches of 4+ PRs, checkpoint + context_reset after each wave block is written. The main thread resumes by reading the wave entries in PROJECT.md, not by replaying per-PR diffs. Without this write, the per-PR posting state and residual risks are lost.

## Aggregate

```markdown
## Review Batch Complete — <N> PRs

| PR | Title | Recommendation | Key Finding | Posted |
|----|-------|----------------|-------------|--------|
| #1 |  | approve | Clean — no issues | draft |

### Needs Attention
- PR #<N>: <why it needs manual follow-up>
```

If all PRs are clean, write `All PRs reviewed cleanly`.

## Notes

Reviews are read-only. No worktrees are needed unless an optional external reviewer requires checkout isolation.
