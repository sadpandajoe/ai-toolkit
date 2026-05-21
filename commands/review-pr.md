# /review-pr - Adaptive Team PR Review

@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: Asked to review someone else's GitHub PR.
> **Produces**: Team-reviewed findings, recommendation, and optional GitHub review posting.

Use `--draft` to show the review locally without posting. Use `--auto` to skip confirmations and authorize posting/approval for the reviewed PRs.

## Usage

```
/review-pr <pr-number-or-url>
/review-pr <pr-number-or-url> --draft
/review-pr <pr-number-or-url> --adversarial
/review-pr <pr-number-or-url> --auto
/review-pr 101 102 103
/review-pr --all-open
```

## Contract

- Main thread orchestrates; reviewer judgment comes from fresh reviewer contexts.
- Read full changed-file context, not only the diff.
- Emit a Complexity Gate block for single-PR reviews.
- Assess impact before calibrating severity.
- Validate PR premise for Standard or CORE-impact PRs.
- Show findings and severity reasoning to the user before posting unless `--auto` is passed.
- Post only clean, user-confirmed finding text to GitHub.
- For batch reviews, keep the main thread as a thin orchestrator and use compact per-PR handoffs.
- For batch reviews of 4+ PRs, follow `rules/context-management.md`: after each wave of 3 PRs, the main thread must append a `## Review-PR Batch Wave N` block to PROJECT.md (per-PR recommendation, posted status, top finding, residual risk), then `/checkpoint --clear` before launching the next wave. This is a hard gate — without the PROJECT.md write, the per-PR posting state is lost on clear.
- For every reviewed PR (single or batch), append a `## PR Review — #N` entry to PROJECT.md before the chat summary. This is a hard gate so `/clear` or `/archive-project-file` immediately after `/review-pr` does not lose the review record.

## Steps

### 1. Resolve Input

Detect whether the input is a single PR, multiple PRs, or `--all-open`.

For multiple PRs or `--all-open`, follow [skills/review/references/pr-batch.md](../skills/review/references/pr-batch.md) and stop after the aggregate summary.

Batch mode should group independent PRs into small waves only when context does not overlap. Do not carry full per-PR diffs in the main thread; keep compact findings, recommendation, blockers, and posting state.

### 2. Single-PR Review

Follow [skills/review/references/pr-review.md](../skills/review/references/pr-review.md).

That reference owns:
- PR context gathering
- Complexity Gate classification
- impact assessment
- premise validation
- reviewer-team dispatch
- pattern analysis
- synthesis, scoring, and recommendation

Use fresh reviewer subagents for each single-PR review pass. Reuse a reviewer only to clarify that reviewer's own finding in the same pass.

### 3. Post or Draft

Follow [skills/review/references/pr-posting.md](../skills/review/references/pr-posting.md).

Respect:
- `--draft`: never post
- `--auto`: skip confirmations and authorize posting/approval for this review
- clean Standard reviews: confirm before approving unless `--auto`
- findings: post only user-confirmed finding descriptions

### 4. PROJECT.md Update (Hard Gate)

Before emitting the chat summary, append a `## PR Review — #N` entry per reviewed PR to PROJECT.md:

```markdown
## PR Review — #[number]
Verdict: [approve / request-changes / comment]
Top finding: [one-liner, or "none"]
Severity counts: [critical N, major N, minor N, nit N]
Posted: [yes / draft / no — reason]
Residual risk: [one-liner, or "none"]
```

Batch waves already write `## Review-PR Batch Wave N`; the per-PR entries can be folded into that wave block instead of duplicated.

Emit before the chat summary:

```markdown
## PROJECT.md Updated — PR Review(s)
PRs recorded: [#numbers]
```

### 5. Summary

Do not emit the chat summary until the `## PROJECT.md Updated — PR Review(s)` block has been emitted.

Emit the summary from [skills/review/references/pr-posting.md](../skills/review/references/pr-posting.md).

## Non-Negotiable Gates

- [ ] Full file context read
- [ ] Complexity Gate block emitted for single PRs
- [ ] Impact assessment completed
- [ ] Premise validation completed for Standard or CORE-impact PRs
- [ ] All findings tagged by severity
- [ ] Recommendation determined before posting
- [ ] Posting action respects `--draft`, `--auto`, and user-confirmation boundaries
- [ ] PROJECT.md `## PR Review — #N` entry written for every reviewed PR before summary
- [ ] Summary emitted

## Notes

- Batch mode defaults to draft/summary output. It posts or approves only when the user passes `--auto` or explicitly authorizes posting.
- Read-only reviews should not mutate the worktree.
- For security-sensitive areas, suggest or run the adversarial lane when appropriate.
