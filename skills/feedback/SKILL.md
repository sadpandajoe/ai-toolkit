---
name: feedback
description: Addressing GitHub PR review feedback — triage reviewer comments, decide which to fix or skip, draft replies, and resolve review threads. Do NOT use for reviewing someone else's PR (use review/), bug fixing without review comments (use debug/ + implement-change/), or manual PR QA (use qa/).
---

# Feedback

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella skill for addressing PR review feedback. The orchestrator keeps the top-level flow, while these references hold the detail.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Gather + triage | Fetch review comments, verify claims, classify fix/skip/discuss | [references/gather-triage.md](references/gather-triage.md) |
| Fix + review | Apply approved fixes, choose commit strategy, run review gate | [references/fix-review.md](references/fix-review.md) |
| Reply + resolve | Draft/post replies, handle identity, resolve bot threads, summarize | [references/reply-resolve.md](references/reply-resolve.md) |

## Invocation Pattern

`address-feedback` is the main entry point. It should read only the phase reference it needs next, and checkpoint before context grows beyond the current review round.

For large review rounds, keep the main thread as orchestrator:
<!-- aitk-model-route:feedback.comment-fix-groups -->
- Send independent comment groups to implementation subagents on `implementation`.
- Keep comment ids, verdicts, and post status in the main thread.
- Require each subagent to return a compact handoff with changed files, comments addressed, tests run, residual risk, and reply draft.

## Notes

- Always verify reviewer claims against code before accepting or rejecting them.
- Human reviewer threads stay open unless the user explicitly asks to resolve them.
- Bot threads are eligible for resolution only when the fix is verified and posting/resolution was authorized for this run.
