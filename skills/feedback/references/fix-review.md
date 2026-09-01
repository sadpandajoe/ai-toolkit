---
tier: Heavy
---

# Fix + Review PR Feedback

## Fix Order

Address approved fixes in this order:

1. Bugs and security issues.
2. Missing error handling or data integrity checks.
3. Project standards and mechanical cleanup.

Use TDD for behavioral changes when feasible: write the failing test first, then fix it. Cosmetic or pattern-following edits may be fixed directly when existing coverage is enough.

## Large Review Rounds

When approved fixes are independent, keep the main thread as the orchestrator:

- Group comments by file, subsystem, or originating commit.
- Batch 2-4 small groups per wave; use single-item waves for risky behavior changes.
- Give subagents only the relevant comments, files, diff context, and expected validation.
- Require a compact handoff: comments addressed, changed files, tests run, reply draft, residual risk.

The main thread owns final review, posting, thread resolution, and user-facing summary.

## Verify Fixes

Before the Review Gate, verify each fix wave through
`skills/verification-loop/SKILL.md` against gate name `address-feedback-verify`
(evidence: the wave's test/build/lint output; `required_criteria`: the
project's existing checks pass for the touched scope). Follow its
RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`, escalate cost
tier per `rules/gates.md`'s autonomous ladder on `ESCALATE` — before moving to
the Review Gate below.

## Review Gate

Run `review-code` on changed files after substantive fixes reach
`address-feedback-verify: PASS`. Translate its findings into a `rules/gates.md`
Gate block via the Mapping From the Old Mechanisms section, the same
substitution `address-feedback`'s own Steps make: the former review-status
vocabulary's `clean`/`micro-fix` → `PASS`; `skipped` → `PASS` with the skip
reason in `Reason`; `blocked` → `BLOCKED`; `user decision` → `USER_DECISION`;
the same finding recurring after a fix attempt → `ESCALATE`.

For truly minimal edits, such as typo fixes or mechanical renames, review may be skipped under the review-gate skip rule. State the skip reason.

## Commit Strategy

Prefer fixing the originating in-PR commit when the branch is not merged and the source commit is clear.

New commits on the current PR branch and pushes are part of the default `address-feedback` flow — apply the recommended shape and push once verification is clean. Amend, rebase, and force-push still require explicit user authorization for this feedback round (the unattended default does not grant history mutation).

| Scenario | Action |
|----------|--------|
| Fix corrects one prior in-PR commit | `git commit --fixup=<originating-sha>` then autosquash rebase |
| Fix spans multiple originating commits | Fix up earliest affected commit, or ask user |
| Fix is additive beyond original scope | New commit |
| Branch is shared or active re-review is underway | New commit; avoid rewriting history |

Autosquash mechanics:

```bash
git commit --fixup=<originating-sha>
git rebase --autosquash <base>
git push --force-with-lease
```

Force-push only after explicit user authorization, only on the current feature branch, and only with `--force-with-lease`. Never force-push main/master or a protected branch.

## Fix Wave Record (Parent-Owned Write)

This reference does not write PROJECT.md itself — `skills/goals/
address-feedback/SKILL.md` appends the `## Feedback Round N` entry after
calling this procedure. Produce these fields so the parent has everything it
needs to write that entry before checkpoint + context_reset can fire:

```markdown
## Feedback Round N
Wave: [comment ids addressed]
Files changed: [list]
Tests: [added/updated/none]
Verification: [address-feedback-verify Gate state + result]
Review Gate: [status]
Residual risk: [...]
Next: [next wave / posting / done]
```

This block is what `start` reads to resume mid-feedback-round after a clear. Without it, the comment-id → fix-state mapping is lost.

## Stop Conditions

Stop before push/post when:

- `--draft` was passed.
- A `Discuss` verdict needs the user's wording or decision.
- Push would require unsafe history rewriting.
- Verification failed or could not run and the change is substantive.
