---
name: address-feedback
description: Work through review comments on your own GitHub PR. Inventory every reviewer and bot, verify each claim, fix or rebut with evidence, push, reply, and resolve bot threads. Use when a PR has review comments to address. Do NOT use for reviewing someone else's PR (use review), CI failures without comments (use fix-ci), or an unattended watch (use watch-pr).
---

# Address PR Feedback

Start from the PR as it is now (diff, comments, CI), not from the session that
wrote it. Commands, the bot list and the rerun check are in
[references/github.md](references/github.md).

## Inventory first

Before judging anything, list every source: which humans commented or
requested changes, which bots commented, each author's top-level, review-body
and inline counts, unresolved threads, and any expected reviewer who is
missing.

## Triage

Each comment gets **Fix**, **Skip** (with evidence why the code is right) or
**Discuss** (a trade-off or product decision the user owns). Keep the triage
table, with comment ID, reviewer, verdict, reason and evidence, in the final
summary.

When you and a reviewer disagree on architecture or a subtle correctness
point, get a tie-break from the `review` skill's second opinion rather than
your own reading.

## Fix

After substantive fixes, run the `review` skill on them; typo-level edits
don't need it.

Every fix is a new commit on the PR branch, whatever commit it corrects.
Rewriting history (`git commit --fixup=<sha>`, `git rebase --autosquash
<base>`, `git push --force-with-lease`, on this feature branch only) happens
only when the user authorized it for this round.

## Push, reply, resolve

Invoking this skill authorizes, for this PR only:
- pushing new commits to its branch;
- posting replies;
- resolving bot threads whose fix is verified and on the branch.

It does not authorize amend, rebase or force-push, approving, or requesting
changes.

- Check `gh auth status` before posting. If `gh` is signed in as a teammate or
  automation account, confirm first.
- Claim a fix in a reply only once it is on the PR branch. Keep replies short
  and evidence-based: "Fixed in `<sha>`: added a null guard before reading the
  payload."
- **Human threads are never resolved here.** Reply, and let the reviewer
  resolve or re-review. Ambiguous or discussion threads stay open unless the
  user asks.
- Pause for the user when a human-thread reply or a Discuss verdict needs
  their wording, the push target is not the current PR branch, verification
  failed or could not run on a substantive fix, or the next step would
  rewrite history, approve, or request changes.

`--draft` drafts replies and resolutions without pushing, posting or
resolving. `--step` shows the push and post plan and waits for approval.
