# Fix + Review PR Feedback

## Large Review Rounds

When approved fixes are independent, keep the main thread as the orchestrator:

- Group comments by file, subsystem, or originating commit.
- Batch 2-4 small groups per wave; use single-item waves for risky behavior changes.
- Give each group only its comments, files, diff context, and expected validation.
- Require a compact handoff: comments addressed, changed files, tests run, reply draft, residual risk.

The main thread keeps comment ids, verdicts and post status, and owns final
review, posting, thread resolution, and the user-facing summary.

## Review Gate

Run `review-code` on changed files after substantive fixes; it emits the `## Gate: review` block from `rules/gates.md`.

For truly minimal edits, such as typo fixes or mechanical renames, the review exception in `rules/gates.md` applies. State the reason.

## Commit Strategy

Prefer fixing the originating in-PR commit when the branch is not merged and the source commit is clear.

New commits on the current PR branch and pushes are part of the default `address-feedback` flow — apply the recommended shape and push once verification is clean. Amend, rebase, and force-push still require explicit user authorization for this feedback round (the unattended default does not grant history mutation).

| Scenario | Action |
|----------|--------|
| Fix corrects one prior in-PR commit | `git commit --fixup=<originating-sha>` then autosquash rebase |
| Fix spans multiple originating commits | Fix up earliest affected commit, or ask user |
| Fix is additive beyond original scope | New commit |
| Branch is shared or active re-review is underway | New commit; avoid rewriting history |

```bash
git commit --fixup=<originating-sha>
git rebase --autosquash <base>
git push --force-with-lease
```

Force-push only after explicit authorization, only on the current feature
branch, and only with `--force-with-lease`; never on main/master or a
protected branch (the git guard hook blocks it).

## Persist Fix Wave to PROJECT.md (Hard Gate Before Handoff)

After each fix wave, before any checkpoint, append:

```markdown
## Feedback Round N
Wave: [comment ids addressed]
Files changed: [list]
Tests: [added/updated/none]
Verification: [STRONG/PARTIAL/WEAK + result]
Review gate: [PASS | RETRY | ESCALATE | USER_DECISION]
Residual risk: [...]
Next: [next wave / posting / done]
```

This block is what `start` reads to resume mid-feedback-round in a fresh session or worker. Without it, the comment-id → fix-state mapping is lost.

Before pushing or posting, check the pause list in [reply-resolve.md](reply-resolve.md#push--post-defaults).
