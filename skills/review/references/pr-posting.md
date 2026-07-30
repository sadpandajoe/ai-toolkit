---
tier: Standard
---

# PR Review Posting

Use after PR review synthesis has produced a recommendation.

## Posting Rules

Detail level scales with complexity and findings.

- **Trivial + clean**: return an approve recommendation; post/approve directly only with `--auto` or explicit user authorization.
- **Moderate + clean**: approve with compact summary in draft/confirmation mode; post directly only with `--auto`.
- **Standard + clean**: pause with a one-line confirmation before approving unless `--auto` was passed.
- **Any findings**: post only user-confirmed findings with adjusted severities.
- **`--draft`**: show review in conversation only. Do not post.
- **`--auto`**: skip confirmations and post/approve directly.

Reasoning, confidence, and internal evidence shown to the user are not posted to GitHub. GitHub gets clean finding descriptions only.

- **Severity labels are internal metadata.** Keep the canonical `[major]`,
  `[minor]`, and `[nitpick]` tags — plus aliases such as `[critical]` or
  `[nit]` — in local synthesis and summaries. Never include scores or confidence
  anywhere in posted GitHub review prose. Never include severity labels in
  inline comments, top-level comments, or review bodies unless the user
  explicitly requests labeled comments.

Use `gh api repos/{owner}/{repo}/pulls/{number}/files --paginate` for accurate diff positions.

## Voice

A posted comment is read by a tired engineer. The defaults below keep findings short, collaborative, and free of the tells that mark a comment as machine-written.

- **Default register is a question, not a verdict.** Make the author justify the asymmetry instead of dictating the fix: "I see X here; the sibling does Y — why the difference?" Reserve declarative phrasing for blocking issues.
- **Strength of ask scales with severity.** Question form for nitpicks ("Did we mean to update this?"), "we should" / "can we" for should-fix items, plain declarative for blockers. Speak to the code, never the author ("you forgot" → "this misses").
- **Length cap: 1–2 sentences per finding.** Past ~50 words it reads as an essay. Cite `file:line` and name the sibling, helper, or prior pattern so the author doesn't have to hunt — the anchor already carries the location, so don't restate it.
- **No code blocks by default.** Add a `suggestion` block only when the fix is non-obvious *and* the severity is should-fix or higher. For a missing test, point at the technique in one sentence; paste a full test only when the mocking/setup is genuinely non-obvious.
- **Match the author's own posting voice when one is observable.** Before posting, glance at the PR author's (or repo's) recent review comments and mirror their length and register. A house style beats a generic one.
- **Cut the AI tells:** scaffolding labels ("Result:", "Worth noting:"), walking the author through code they wrote, restating the PR description back at them, over-hedging, double negatives ("would no longer fail"), and stacking nitpicks to pad the review. A review with only nitpicks is an approval dressed up — say "approve" instead.

## Security Suggestion

If `--adversarial` was not used and the diff touches security-sensitive areas (auth, input handling, API endpoints, database queries, file operations, secrets), suggest re-running with `review-pr <ref> --adversarial` or `review-code-adversarial`.

## Summary Shape

```markdown
## Review-PR Complete
PR #<number>: <title> — <Approve / Request Changes / Comment>

### Team Selected
| Reviewer | Why |
|----------|-----|
| Code quality | Always |

### Scores
| Component | Score |
|-----------|-------|
| Root Cause | X/10 |
| Solution | X/10 |
| Tests | X/10 |
| Code | X/10 |
| Docs | X/10 |
| Overall | X/10 |

### Issues Found
- <N> major, <N> minor, <N> nitpick

### Posted
<Yes — link / No — draft mode>

### Suggested Next Steps
- <specific next action>
```

Suggested next step examples:
- Approved: PR is ready to merge.
- Request Changes posted: wait for author to address, then re-run `review-pr`.
- Comment posted: author should review comments; re-run when updated.
- Draft mode: post with `review-pr <number>` without `--draft`.
- Security-sensitive: re-run with `--adversarial`.
- Author asked you to address feedback: `address-feedback <number>`.
