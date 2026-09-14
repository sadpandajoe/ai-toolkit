# Address PR Review Feedback

> **When**: A PR has review comments to investigate, fix, reply to, or resolve.
> **Produces**: Evidence-based triage, verified fixes, reviewer replies, and a feedback-round summary.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `address-feedback`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Usage

```bash
address-feedback <pr-number-or-url> [--draft] [--step]
```

The default runs unattended for bot and posting work: new commits, pushes to
the current PR branch, replies to bot threads, resolution of eligible bot
threads once fixes are verified. Invariant pauses on every path: human-thread
reply wording, amend/rebase/force-push, ambiguous push target, failed
verification, approve or request-changes. `--step` restores confirmations.

## Authorization Boundary

Authorization mode: `invocation`. The invocation grants only the documented
default commit, current-branch push, bot reply, and eligible thread resolution
scope; every invariant pause still requires explicit input.

## Goal Loop

Start from the PR state (diff, comments, CI), not from the original
implementation session. Load the `feedback` skill phase by phase.

1. **Inventory and triage** with `feedback/references/gather-triage.md`. Emit
   the Reviewer Inventory table first; then investigate each thread and decide
   fix, skip, or discuss with evidence. Reject incorrect suggestions with
   evidence rather than complying. Persist `## Feedback Triage` (hard gate).
2. **Classify complexity** of the accepted fixes and persist the snapshot.
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
   PII scrub over every reply, comment, and commit message. Persist
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

Record a `metrics-emit` event with the fields from `reply-resolve.md`.
