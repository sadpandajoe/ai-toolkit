# Reply + Resolve PR Feedback

## Draft Replies

Keep replies short and evidence-based.

```markdown
Fixed in `<sha>` - added a null guard before reading the response payload.
```

```markdown
Thanks for the suggestion. Keeping the current approach because auth is enforced by the route middleware before this handler runs.
```

```markdown
Good question. This would change the API contract for existing callers; should we make that behavior change in this PR or open a follow-up?
```

Scrub every reply, top-level comment and commit message under
`rules/pii-scrub.md` before posting.

## Posting Rules

Each post, resolution and push is a provider operation that a resumed session
must not repeat (N14). Before it, run `bin/aitk project-state op --check
<id>`: exit 0 means it already ran, so skip it; exit 3 means it has not, so
post it and then record it with `bin/aitk project-state op --id <id>`; any
other exit stops. The ids are `reply:<comment-id>`, `resolve:<thread-id>` and
`push:<sha>`.

1. Inline reply for line-anchored review comments with a path, line, and comment id:

```bash
gh api repos/<owner>/<repo>/pulls/<number>/comments/<comment-id>/replies \
  -f body="<response>"
```

2. Do not reply to top-level review body summaries unless they ask a direct code question.
3. For a top-level direct code question, use a normal PR comment and quote enough context.
4. Check identity with `gh auth status` before posting. If `gh` is
   authenticated as a teammate or automation account that could surprise the
   user, pause and confirm.

## Resolve Threads

- Bot threads are eligible for resolution only when the associated fix is verified and resolution was authorized for this run.
- Human reviewer threads are never resolved here. Post the reply and let the reviewer resolve or re-review.
- Never resolve ambiguous or discussion threads unless the user explicitly asks.

## Push + Post Defaults

Default behavior: push new commits on the current PR branch, post replies to bot threads, and resolve eligible bot threads once the underlying fix is verified. Approve / request-changes always confirms with the user.

Pause for explicit confirmation when:
- a human-thread reply or a `Discuss` verdict needs the user's wording or decision
- the next git step would amend, rebase, or force-push history
- the push target is ambiguous (not the current PR branch, or tracks an unexpected remote)
- the next action would approve or request changes on the PR
- verification failed or could not run on a substantive change, or the fix is not yet on the PR branch

Flag meanings:
- `--draft`: never push, post or resolve; return reply drafts and resolution recommendations only.
- `--step`: announce the post/resolve plan in one block and wait for approval before posting or resolving.
- No flag (default): skip the per-step posting confirmation for verified bot threads and the push announcement once verification is clean and identity checks pass. Does NOT authorize amend, rebase, or force-push. `--auto` is a legacy no-op alias for this default.

Claim a fix in a reply only after it is on the PR branch, unless the user
explicitly asks to post draft wording before pushing.

When confirmation is needed, pause with:

```markdown
Ready to push [N] commits and reply to [N] threads:
- Fixed: [...]
- Skipped: [...]
- Discuss: [...]
Push and post?
```

Record metrics with `bin/aitk metrics emit --workflow address-feedback
--status <PASS | ESCALATE | USER_DECISION | BLOCKED | skipped>` (`skipped`
when no comment was actionable) and `--workers <route>=<n> …`; complexity,
gates, retries, and escalations come from the snapshot.
