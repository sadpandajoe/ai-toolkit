---
name: feedback
description: Addressing GitHub PR review feedback — triage reviewer comments, decide which to fix or skip, draft replies, and resolve review threads. Do NOT use for reviewing someone else's PR (use review/), bug fixing without review comments (use debug/ + implement-change/), or manual PR QA (use qa/).
---

# Feedback

Umbrella skill for addressing PR review feedback. `address-feedback` is the
entry point and reads only the phase reference it needs next.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Gather + triage | Fetch review comments, verify claims, classify fix/skip/discuss | [references/gather-triage.md](references/gather-triage.md) |
| Fix + review | Apply approved fixes, choose commit strategy, run review gate | [references/fix-review.md](references/fix-review.md) |
| Reply + resolve | Draft/post replies, handle identity, resolve bot threads | [references/reply-resolve.md](references/reply-resolve.md) |

<!-- aitk-model-route:feedback.comment-fix-groups -->
Large rounds send independent comment groups to implementation workers on `implementation`; see [Large Review Rounds](references/fix-review.md#large-review-rounds).

## Notes

- Human reviewer threads stay open unless the user explicitly asks to resolve them.
- Bot threads are eligible for resolution only when the fix is verified and posting/resolution was authorized for this run.
