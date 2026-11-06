---
name: create-pr
description: Push the current feature branch and open a draft GitHub PR with a human-readable title and body written from the commits, the diff and the repo's template. Use when the work is done and the user wants a PR. Do NOT use for marking a PR ready, requesting reviewers or merging (those need the user's own words), or for reviewing a PR (use review).
---

# Create a PR

Invoking this skill authorizes pushing the current feature branch and opening
one **draft** PR for it, never from `main`. If the branch already has an open
PR (`gh pr view --json number,url,isDraft`), reuse it as it is: never run
`gh pr ready` or `gh pr edit` on it. A ready (non-draft) PR, reviewers and
merging are the user's to do: the git guard allows them only when the user
started the session with `AITK_PR_READY=1`, and blocks a command that sets
it.

## Before opening

Open the PR when you are confident it is correct: the change's tests and the
repo's checks ran green on this tree, and anything risky had a `review`. A UI
change needs its before and after screenshots or video in hand; capture them
with the `test-pr` skill. `gh` cannot upload images,
so list the media files under the test plan and tell the user to drag them in,
unless the repository has another convention.

## Title

Follow the repository's convention (`gh pr list --state merged --limit 5
--json title`). Lead with the most user-visible outcome for the affected area
rather than the mechanism. When the PR adds an entry point, name the one a
caller would search for. Keep it near 70 characters so PR lists show it whole.

## Body

Fill the repository's PR template when there is one
(`.github/pull_request_template.md` or a sibling path). Otherwise use:

- **Summary**: what changed and why, for a reader who doesn't know the
  codebase;
- **Changes**: grouped by area, not a file list;
- **Test plan**: what ran, plus the UI media;
- **Related**.

For a bug fix with a confirmed root cause, replace Changes with **Incident
Root Cause**, **Latent Bugs / Hardening** (omit when there are none) and
**Fix**. That keeps the blocking cause apart from opportunistic hardening.

Describe the PR as it stands, not how it was built, and make the body as long
as the change needs. Use only terms a reader can find in the code, the commits
or the docs. A label coined while planning ("Tier A", "channel-3", "skeleton
commit") means nothing on a public PR, so say what it stood for.

## Scrub, then open

Re-read the title and body for PII:
- Shortcut `sc-XXXXX`, Linear or Jira IDs;
- tracker links, internal dashboards, staging workspaces and customer
  instances;
- customer or workspace names;
- reporter identity;
- credentials, including in repro snippets.

The rule holds in private repositories too. If the scrub rewrote anything,
show the rewrite and wait for confirmation. Otherwise go ahead:

```bash
git push -u origin HEAD
gh pr create --draft --title "<title>" --body-file <file> [--base <branch>]
```

Report the PR number, URL, base and draft state.

With `--watch`, go straight into `watch-pr` on the new PR; the flag is the
user's grant for that skill's standing pushes. Without it, if the PR has CI
checks, end with one line suggesting `watch-pr`. Never start watching on your
own initiative.
