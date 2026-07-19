# Address PR Review Feedback


> **When**: A PR has review comments that need investigation, fixes, replies, or thread handling.
> **Produces**: Evidence-based triage, approved fixes, verification, reviewer replies, and a final feedback-round summary.

## Effect Boundary

Effect: `external_effect`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `address-feedback`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Usage

```bash
address-feedback <pr-number-or-url>
address-feedback <pr-number-or-url> --draft
address-feedback <pr-number-or-url> --step
```

The default runs unattended for bot/posting work: no post-triage pause, no per-post confirmations — it creates new commits, pushes them to the current PR branch, posts replies to bot threads, and resolves eligible bot threads once fixes are verified. Invariant pauses on every path: human-thread reply wording, amend/rebase/force-push, ambiguous push target, failed verification, and approve/request-changes. `--step` restores the post-triage confirmation and the post/resolve announcement for a supervised round. `--auto` is a legacy no-op alias for the default.

## Authorization Boundary

Authorization mode: `invocation`. The workflow invocation grants only the
documented default commit, current-branch push, bot reply, and eligible thread
resolution scope; every invariant pause above still requires explicit input.

## Routing

Use the `feedback` skill phase-by-phase. Do not preload every reference up front:

1. Gather comments and triage with [skills/feedback/references/gather-triage.md](../../feedback/references/gather-triage.md). Step 1 must emit an explicit **Reviewer Inventory** table before any triage starts:

   ```
   ## Reviewer Inventory
   | Author | Type | Open threads | Notes |
   |--------|------|--------------|-------|
   ```

   Include every distinct comment author (humans + bots) and the per-author open-thread count. Cross-check against the known-bot list in `gather-triage.md`; do not proceed to triage if any expected reviewer is missing or inaccessible.

2. Apply approved fixes and run review with [skills/feedback/references/fix-review.md](../../feedback/references/fix-review.md).
3. Draft/post replies and resolve eligible bot threads with [skills/feedback/references/reply-resolve.md](../../feedback/references/reply-resolve.md).

## Orchestration Model

The main thread owns PR state: comment ids, triage verdicts, posting decisions, thread resolution, and final summary.

<!-- aitk-model-route:workflows.feedback-fix-wave -->
For large review rounds, batch independent fixes into subagent waves only when ownership is disjoint. Send each subagent on `implementation` only the relevant comments, files, current diff, validation expectation, and reply-draft requirement. The subagent returns a compact handoff; the main thread reviews, verifies, and posts.

For STANDARD or expensive feedback rounds, checkpoint + context_reset after triage decisions are recorded, after each fix wave, and after `review-code` fixes when posting/re-resolution work remains. Resume from PROJECT.md plus the comment id/verdict table rather than carrying the whole review discussion in chat.

**Hard gate — PROJECT.md write before any clear.** Each of the three boundaries below requires a PROJECT.md write *before* checkpoint + context_reset fires. Clearing without the write throws away the comment-id verdict map that resume depends on.

- After triage: append `## Feedback Triage` with the full Reviewer Inventory table + comment-id → verdict map.
- After each fix wave: append `## Feedback Round N` (comments addressed, files changed, verification result, residual risk).
- After posting/resolution: append `## Feedback Posted` (per-thread post + resolve status).

For STANDARD work, emit the Phase Plan block from `rules/complexity-gate.md` immediately after the Complexity Gate.

## Gates

- Start with the mandatory reviewer/bot inventory from `feedback/references/gather-triage.md`; do not triage only the first visible comments.
- Emit a Complexity Gate before fixing.
- Investigate before triage; never accept or reject comments by guess.
- Pause after triage only when `--step` was passed; otherwise emit the triage table and proceed.
- Run `verify` or equivalent pre-flight checks before `review-code`, and record the result in the Review Gate.
- Use the Review Gate skip/micro-fix exceptions only when `rules/review-gate.md` allows them; otherwise run `review-code` after substantive fixes.
- Default action: create a new commit on the current PR branch, push it, post replies to bot threads, and resolve eligible bot threads once the underlying fix is verified.
- Pause for explicit user confirmation when any of these apply: `--draft` was passed, a human-thread reply needs user wording, verification failed, the fix is not yet visible on the PR branch, the next git step would amend/rebase/force-push, the push target is ambiguous (not the current PR branch, or tracks an unexpected remote), or the next action would approve / request changes on the PR.
- Run the PII scrub from `feedback/references/reply-resolve.md` over every drafted reply, top-level comment, and commit message before posting or pushing. Strip customer names, internal ticket IDs (Shortcut/Linear/Jira), internal URLs, reporter identity, and credentials.

## Summary Contract

End with:

```markdown
## Address-Feedback Complete
PR #[number] - [N] fixed, [N] skipped, [N] discussed

### Actions Taken
- Fixed: [...]
- Skipped: [...]
- Discussed: [...]

### Verification
- [...]

### Posting
- [...]

### Suggested Next Steps
- [...]
```

Record a `metrics-emit` event using the [metrics emitter](../../metrics-emit/SKILL.md) and the fields from `feedback/references/reply-resolve.md`.
