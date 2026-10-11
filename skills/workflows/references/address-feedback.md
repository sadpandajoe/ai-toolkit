# Address PR Review Feedback

> **When**: A PR has review comments to investigate, fix, reply to, or resolve.
> **Produces**: Evidence-based triage, verified fixes, reviewer replies, and a feedback-round summary.

## Effect Boundary

Effect: `external_effect`.

Authorization mode: `invocation`.

## Durable Runtime Contract

`address-feedback` in `interfaces/contracts.json`; transitions and effects go
through `bin/aitk checkpoint`.

## Authorization Boundary

```bash
address-feedback <pr-number-or-url> [--draft] [--step]
```

The invocation grants the push and post defaults in
`feedback/references/reply-resolve.md`, and nothing more. Its invariant pauses,
human-thread reply wording first, still need explicit input on every path;
`--step` restores the per-step confirmations.

## Goal Loop

Start from the PR state (diff, comments, CI), not from the original
implementation session. Load the `feedback` skill phase by phase.

1. **Inventory and triage** with `feedback/references/gather-triage.md`. Emit
   the Reviewer Inventory table first; then investigate each thread and decide
   fix, skip, or discuss with evidence. Reject incorrect suggestions with
   evidence rather than complying. Persist `## Feedback Triage` (hard gate).
2. **Classify complexity** of the accepted fixes and persist it with
   `bin/aitk project-state init --workflow address-feedback ... --format
   block`; paste the Complexity Gate block it prints.
3. **Fix** with `feedback/references/fix-review.md`.
   <!-- aitk-model-route:workflows.feedback-fix-wave -->
   For large rounds with disjoint ownership, launch fresh implementer workers on
   `implementation`, one per independent comment group, each with only its
   comments, files, diff context, validation expectation, and reply-draft
   requirement; each returns a compact handoff. Otherwise fix inline.
4. **Verify** with `skills/verification-loop/SKILL.md`, then `review-code`
   after substantive fixes (review exception for typo-level edits). Persist
   `## Feedback Round N`.
5. **Tie-break** architectural or subtle-correctness disagreements with a
   reviewer through one independent lane (`review/references/local-review.md`
   independent review) rather than the parent's opinion.
6. **Reply and resolve** with `feedback/references/reply-resolve.md` after the
   PII scrub over every reply, comment, and commit message. Before each reply,
   resolution and push, `bin/aitk project-state op --check <id>` skips one
   that already ran; record each with `op --id <id>` after it succeeds
   (`reply:<comment-id>`, `resolve:<thread-id>`, `push:<sha>`). Persist
   `## Feedback Posted`.

## Summary

```markdown
## Address-Feedback Complete
PR #<n> — <fixed> fixed, <skipped> skipped, <discussed> discussed
### Actions Taken
### Verification
### Posting
### Suggested Next Steps
```

Record metrics with `bin/aitk metrics emit --workflow address-feedback --status
<terminal status>`, adding the fields `reply-resolve.md` names with `--extra`.
