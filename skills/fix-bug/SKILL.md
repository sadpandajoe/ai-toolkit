---
name: fix-bug
description: Fix a reported bug end to end — establish the root cause with evidence, fix it with a regression test, and open a draft PR. Use for a bug report, regression, error, or bug ticket (sc-12345, a GitHub issue or URL). Do NOT use for failing CI checks (use fix-ci) or new features (use build-feature); when the user only asks why something happens, report the diagnosis and stop.
---

# Fix Bug

## Before investigating

- Fetch a Shortcut reference (`sc-12345`, an `app.shortcut.com` URL) with the
  `shortcut` skill.
- Check whether the bug is already fixed. Look at:
  - main-branch commits that touch the affected files or name the bug;
  - merged PRs that match;
  - an open PR that contains the fix;
  - the release branch, when the repository maintains several lines.

  Fixed upstream: backport it with the `cherry-pick` skill. A fix pending in an
  open PR is not a fix. Stop and show the user that PR, since adopting,
  monitoring or superseding it is their call. Skip this check for dependency
  bumps and refactors, unless the bump exposed a pre-existing bug; that bug is
  then the subject.
- Scope history to the main branch, the current branch and merged PRs. Never
  run `git log --all`: unmerged branches hold code that never shipped. To read
  removed code, find the removal commit on main and run
  `git show <sha>^:<file>`.

## Root-cause bar

Don't fix until the root cause is reproduced by a test, script or command (or
the reason it can't be is stated, with the indirect evidence that stands in),
and at least one alternative cause is ruled out with evidence.

Have the root cause checked cold before fixing when any of these hold:
- it wasn't reproduced;
- an alternative is still live;
- the failure is intermittent;
- a fix attempt already failed.

Give a fresh subagent the symptom and the evidence, not your conclusion.

Keep the incident's root cause separate from latent bugs found along the way.
Sometimes the client did something unsafe that the endpoint allowed: missing
pagination, a missing scoping filter, an unbounded batch. Then ask whether the
endpoint should enforce the property too, by defaulting or capping page size,
validating scoping, or capping batch size. List it as a latent finding, and fix
it only if the user accepts.

## Fix

- A regression test is required; skipping it needs the user to accept the
  gap explicitly.
- A risky fix (as the `review` skill defines it) gets a second opinion from
  the `review` skill before the PR.

## PR

Open a draft PR with the `create-pr` skill. Its description leads with
**Incident Root Cause**, then **Latent Bugs / Hardening** when there are any.
User-visible fixes carry the before/after evidence the toolkit rules require;
capture it with the `test-pr` skill, starting with **before** while the app
still runs the unfixed code. For work that spans
sessions, keep notes per the `handoff` skill.
