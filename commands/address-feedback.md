# /address-feedback - Address PR Review Feedback

@{{TOOLKIT_DIR}}/rules/complexity-gate.md

> **When**: A PR has review comments that need to be addressed.
> **Produces**: Fixes committed, responses posted, threads resolved.

Use `--draft` to show responses locally without posting to GitHub.

## Golden Rule
Always investigate before triaging — read the actual code, verify claims, check git blame. Evidence-based triage, not guess-based.

## Usage

```
/address-feedback <pr-number-or-url>
/address-feedback <pr-number-or-url> --draft
/address-feedback <pr-number-or-url> --auto
```

## Steps

### 1. Gather + Complexity Gate

Fetch PR comments:
```bash
gh pr view <number> --comments
gh api repos/<owner>/<repo>/pulls/<number>/comments
```

Classify feedback scope:

| Signal | Trivial | Standard |
|--------|---------|----------|
| Comment count | 1–3 | 4+ |
| Fix type | Cosmetic, naming | Logic, behavior |
| Scope | Single area | Cross-cutting |
| Discussion items | 0 | 1+ |

Emit the Complexity Gate block per `rules/complexity-gate.md`.

**Trivial + confidence 8/10+**: Quick-fix path — fix, post, summary. Skip triage table.

### 2. Investigate + Triage

For each review comment:
- Read the actual code referenced
- Verify the reviewer's claim (don't assume correctness)
- Check if handled elsewhere (guard clause, try/catch, middleware)
- Check git blame for context on why the code exists

Triage each item with full reasoning — present to the user BEFORE taking action:

| # | Reviewer | Comment | Verdict | Reasoning | Confidence |
|---|----------|---------|---------|-----------|------------|
| 1 | @user | ... | Fix | [why this should be fixed — what's the actual risk] | 9/10 |
| 2 | @user | ... | Skip | [why this is not valid — evidence from code, git blame, existing patterns] | 7/10 |
| 3 | @user | ... | Discuss | [why this is ambiguous — what are the trade-offs] | 5/10 |

- **Fix**: bugs, security issues, missing error handling, project standards
- **Skip**: style preferences, out of scope, misunderstanding, incorrect assessment
- **Discuss**: architectural disagreements, ambiguous requirements, trade-offs

**User confirmation gate**: Present the triage table with reasoning and wait for the user to confirm, adjust verdicts, or override. Do not start fixing or posting until the user approves the triage. This prevents wasted work on items the user disagrees with and catches cases where the reviewer's comment is actually correct but Claude mistriaged it.

**`--auto` flag**: Skip the confirmation gate and proceed immediately with the triage as determined. The triage table is still shown in the summary for transparency, but execution is not paused.

### 3. Fix

Address fixes by priority:
1. Bugs and security issues
2. Missing error handling
3. Standards compliance

**TDD for behavioral changes**: write a test first (RED), then fix (GREEN).
**Direct fix for cosmetic/pattern-following**: fix directly, existing tests cover it.

Stage your changes. Defer the commit shape to the **Commit Strategy** section below — fixup-into-originating is the default for in-PR corrections.

### 4. Review Gate

Run `/review-code` on changed files. The developer emits a Review Gate block per `rules/review-gate.md`.

For truly minimal fixes (renames, typo corrections), the review may be skipped per the skip rule in `rules/review-gate.md`.

### 5. Draft Responses

For each item, draft a reply:

**Fixed**: Short confirmation with commit reference.
```
Fixed in `abc1234` — added null guard for `getData()` return value.
```

**Skipped**: Explanation with evidence.
```
Thanks for the suggestion. Keeping the current approach — it follows existing patterns in this area.
```

**Discuss**: Context and question.
```
Good question — auth is handled by middleware upstream. The changes here operate after auth validation.
```

### 6. Commit Strategy

When the fix corrects code introduced by an earlier commit on the same un-merged feature branch, fold the fix into that commit using fixup+autosquash — not a fresh follow-up commit. Bug + fix in one commit means rollback ties them together.

| Scenario | Action |
|----------|--------|
| Fix corrects a prior in-PR commit on this branch (single originating commit clear) | `git commit --fixup=<originating-sha>` + `git rebase --autosquash <base>` + `git push --force-with-lease` |
| Fix spans multiple originating commits on this branch | Fixup against the earliest affected commit, or surface to the user for guidance |
| Fix is genuinely additive (new test, new behavior beyond what the original commit covered) | New commit + push |
| Branch is shared / re-reviews requested mid-flight | New commit + push — don't rewrite history while reviewers are looking |

**Force-push safety**: only permitted on the current feature branch under `--force-with-lease`. Never on main/master or shared branches.

**Mechanics**: see `commands/fix-ci.md` § "Amend mechanics" for the autosquash pattern and the pre-commit-hook ordering caveat.

### 7. Push + Post

**Reply strategy — code-anchored or direct code questions only:**

1. **Inline reply** for line-anchored review comments (has a `path` + `line` + comment `id`). Threads directly under the reviewer's comment:
   ```bash
   gh api repos/<owner>/<repo>/pulls/comments/<comment-id>/replies \
     -f body="<response>"
   ```
2. **No reply** for top-level PR-review body summaries or meta commentary. The new commit + commit message speak for the change; the reviewer sees the diff on next pass. Don't quote-reply on review bodies — it creates noise and (when `gh` is authed as a teammate) appears under the wrong identity.
3. **Quoted reply on a top-level comment** is appropriate ONLY when the comment asks a direct code question. Quote the snippet so context is clear:
   ```bash
   gh pr comment <number> --body "> <quoted question>\n\n<answer>"
   ```
4. **Identity check before posting**: `gh` posts as the authenticated user. If `gh auth status` shows a team member, the comment will appear under their name on the timeline — surface and confirm with the user before any post.

```bash
git push  # or git push --force-with-lease per Commit Strategy
```

**All-mechanical fixes** (typo, config, lint, formatting): Push and post replies automatically. No confirmation needed.

**Substantive fixes** (logic changes, refactors, behavioral changes): Pause with a summary before pushing:
```
"Ready to push [N] commits and reply to [N] threads:
- Fixed: [list]
- Skipped: [list]
Push and post? [Y/n]"
```
Proceed on confirmation.

**`--auto` flag**: Skip all confirmations — push and post immediately (original behavior for scripted use).

**Stop conditions** (present to user instead of pushing):
- `--draft` flag was used
- Any "Discuss" item has genuine ambiguity needing user input before posting
- Push would fail (diverged branch, protected branch)

**Auto-resolve bot threads**: Resolve conversation threads from bot authors (`[bot]` suffix or `type: "Bot"`). Mechanical checks — if the fix passes, the comment is addressed.

**Leave human threads open**: Post the "Fixed in `<sha>`" reply but do not resolve. Human reviewers verify themselves.

### 8. Summary

```markdown
## Address-Feedback Complete
PR #[number] — [N] fixed, [N] skipped, [N] discussed

### Actions Taken
- **Fixed**: [count] items (committed + pushed)
- **Skipped**: [count] items (responses posted)
- **Discussed**: [count] items (responses posted / awaiting user input)

### Suggested Next Steps
[Pick based on current state:]
- **All fixed, pushed**: Request re-review from the reviewer
- **Discuss items pending**: Resolve the open questions, then re-run `/address-feedback`
- **Draft mode**: Push and post with `/address-feedback <number>` (without `--draft`) when ready
- **Reviewer requested more changes**: Wait for next review round, then `/address-feedback` again
- **All resolved, PR approved**: Merge the PR
```

**Record metrics**: include `metrics-emit` context with:
- `command`: `address-feedback`
- `complexity`: classification from the complexity gate (`trivial` / `standard`)
- `status`: outcome (`clean` / `blocked` / `user-decision` / `skipped` / `micro-fix`)
- `rounds`: review rounds if any (0 if review was skipped)
- `gate_decisions`: `{ complexity: <gate>, triage: <fix N / skip N / discuss N>, review: <gate> }`
- `models_used`: subagent model invocation counts

## Non-Negotiable Gates

- [ ] Complexity Gate block emitted
- [ ] Evidence-based investigation before every triage verdict
- [ ] Review Gate block emitted (after fixes, unless skipped per skip rule)
- [ ] Summary emitted

## Notes
- Always investigate before triaging — read the actual code
- TDD for behavioral changes, direct fix for cosmetic/pattern-following
- Default is auto-push and auto-post; use `--draft` for local-only
