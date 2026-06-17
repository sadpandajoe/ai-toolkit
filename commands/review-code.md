# /review-code - Adaptive Team Code Review

@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: You have local changes and want a quality pass with the right reviewers for the change type.
> **Produces**: Team-reviewed findings, fixes, test coverage assessment, verification, a durable PROJECT.md review record, and a Review Gate block.

## Usage

```bash
/review-code                  # branch-wide: committed + uncommitted vs base
/review-code src/api/         # filter to path
/review-code --files a.ts b.ts
/review-code --committed      # committed only (base..HEAD)
/review-code --uncommitted    # uncommitted only (working tree + staged)
```

## Routing

Use [skills/review/references/local-review.md](../skills/review/references/local-review.md) as the workflow reference.

That reference dispatches:

- [skills/review/references/classify-diff.md](../skills/review/references/classify-diff.md)
- [skills/review/references/code-quality.md](../skills/review/references/code-quality.md)
- QA impact assessment
- Testing reviewers when tests or test gaps are in scope
- Plan-review lenses for architecture/frontend/backend concerns

## Orchestration Model

The main thread is the orchestrator. It gathers changed files, runs the Complexity Gate, runs repo-appropriate pre-flight verification, dispatches reviewer subagents **plus an always-on Codex second-opinion lane** (launched concurrently, owned by the main thread), deduplicates findings across all lanes, writes actionable review state to PROJECT.md, applies accepted fixes ("accepted" = confirmed by review synthesis/triage, not a per-fix user pause — only disputed or user-decision findings surface to the user), re-verifies, and emits the Review Gate.

All review judgment comes from fresh-context reviewer lanes. The main thread synthesizes and fixes; it does not replace the reviewers.

Use fresh reviewer subagents for each review pass after material code changes. Reuse a reviewer only to clarify that reviewer's own finding in the same pass.

For STANDARD or expensive reviews, checkpoint/clear before reviewer dispatch once pre-flight verification and diff scope are recorded, and again after review findings or fixes when QA/PR/final reporting remains. Resume from changed-file list, pre-flight result, PROJECT.md review record, and Review Gate state rather than from implementation chatter.

## Gates

- Stop when no changes are found.
- Formatting-only and micro-fix diffs may skip reviewer dispatch only after the `rules/review-gate.md` preconditions, including applicable pre-flight checks, are satisfied.
- CORE impact calibrates severity. TRIVIAL + CORE escalates to the full review team. MODERATE + CORE stays on triggered lanes with stricter severity unless security, data-loss, unclear ownership, or cross-cutting behavior escalates it to STANDARD handling.
- Run `/verify` or equivalent repo-appropriate pre-flight checks before reviewer dispatch, then re-run targeted checks after fixes. Record the final result in the Review Gate.
- Suggest `/review-code-adversarial` when security-sensitive files or inputs are touched.

## Summary Contract

Before fixing or clearing context, write/update PROJECT.md with the compact review record defined in `review/references/local-review.md`. End with the Review Gate and the compact summary defined there.

Internal callers such as `/create-feature`, `/fix-bug`, `/fix-ci`, `/create-tests`, and `/update-tests` own the next-step section after the Review Gate.

## Notes

- This command is used standalone and as an internal review phase.
- The selected team should be visible in the summary so bad selections can be corrected with `/reflect`.
- **Codex always reviews too.** Every run launches an independent Codex second-opinion lane (all tiers) concurrently with the Claude reviewer lanes — see the Codex Second Opinion section in `review/references/local-review.md`. It degrades gracefully: when the Codex plugin/CLI is unavailable, record `Codex: skipped (unavailable)` and continue. The whole-loop skip for formatting-only/micro-fix diffs skips Codex too.
