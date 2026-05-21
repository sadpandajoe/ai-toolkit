# /address-feedback - Address PR Review Feedback

@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: A PR has review comments that need investigation, fixes, replies, or thread handling.
> **Produces**: Evidence-based triage, approved fixes, verification, reviewer replies, and a final feedback-round summary.

## Usage

```bash
/address-feedback <pr-number-or-url>
/address-feedback <pr-number-or-url> --draft
/address-feedback <pr-number-or-url> --auto
```

`--auto` skips triage/posting confirmations where verification is clean. It does not authorize commit, amend, rebase, push, or force-push by itself.

## Routing

Use the `feedback` skill phase-by-phase. Do not preload every reference up front:

1. Gather comments and triage with [skills/feedback/references/gather-triage.md](../skills/feedback/references/gather-triage.md). Step 1 must emit an explicit **Reviewer Inventory** table before any triage starts:

   ```
   ## Reviewer Inventory
   | Author | Type | Open threads | Notes |
   |--------|------|--------------|-------|
   ```

   Include every distinct comment author (humans + bots) and the per-author open-thread count. Cross-check against the known-bot list in `gather-triage.md`; do not proceed to triage if any expected reviewer is missing or inaccessible.

2. Apply approved fixes and run review with [skills/feedback/references/fix-review.md](../skills/feedback/references/fix-review.md).
3. Draft/post replies and resolve eligible bot threads with [skills/feedback/references/reply-resolve.md](../skills/feedback/references/reply-resolve.md).

## Orchestration Model

The main thread owns PR state: comment ids, triage verdicts, posting decisions, thread resolution, and final summary.

For large review rounds, batch independent fixes into subagent waves only when ownership is disjoint. Send each subagent only the relevant comments, files, current diff, validation expectation, and reply-draft requirement. The subagent returns a compact handoff; the main thread reviews, verifies, and posts.

For STANDARD or expensive feedback rounds, checkpoint/clear after triage decisions are recorded, after each fix wave, and after `/review-code` fixes when posting/re-resolution work remains. Resume from PROJECT.md plus the comment id/verdict table rather than carrying the whole review discussion in chat.

**Hard gate — PROJECT.md write before any clear.** Each of the three boundaries below requires a PROJECT.md write *before* `/checkpoint --clear` fires. Clearing without the write throws away the comment-id verdict map that resume depends on.

- After triage: append `## Feedback Triage` with the full Reviewer Inventory table + comment-id → verdict map.
- After each fix wave: append `## Feedback Round N` (comments addressed, files changed, verification result, residual risk).
- After posting/resolution: append `## Feedback Posted` (per-thread post + resolve status).

For STANDARD work, emit the Phase Plan block from `rules/complexity-gate.md` immediately after the Complexity Gate.

## Gates

- Start with the mandatory reviewer/bot inventory from `feedback/references/gather-triage.md`; do not triage only the first visible comments.
- Emit a Complexity Gate before fixing.
- Investigate before triage; never accept or reject comments by guess.
- Pause after triage unless `--auto` was passed.
- Run `/verify` or equivalent pre-flight checks before `/review-code`, and record the result in the Review Gate.
- Use the Review Gate skip/micro-fix exceptions only when `rules/review-gate.md` allows them; otherwise run `/review-code` after substantive fixes.
- Stop before posting when `--draft` was passed, a discussion needs user wording, verification failed, the fix is not visible on the PR branch, or push/post safety is unclear.
- Stop before commit, amend, rebase, push, force-push, GitHub posting, or thread resolution unless the user explicitly authorized that boundary or the command flag clearly grants it.
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

Record a `metrics-emit` event using the fields from `feedback/references/reply-resolve.md`.
