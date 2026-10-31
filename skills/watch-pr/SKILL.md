---
name: watch-pr
description: Watch an open PR unattended. Monitor CI (Actions and external status contexts) and review comments, fix what the PR broke, rerun transient failures, answer bot and clear feedback, and stop when CI is stably green or a human decision is needed. Use when the user asks to watch or babysit a PR. Do NOT use for one-off CI diagnosis (use fix-ci) or a single feedback round (use address-feedback).
---

# Watch a PR

`watch-pr [<pr>] [--greens N] [--no-comments]`

## Authorization

Invoking this skill grants standing authorization, for this PR only, to:
- make fast-forward commits on its head branch and push them;
- post factual replies;
- resolve threads within the scope of `address-feedback`.

It does not authorize amend, rebase, force-push, other branches, merging,
approving or requesting changes. Before the first push, reply or rerun, and
again after a resume, state the grant in one block: the PR, head ← base, the
green target, the comment scope, and what is and isn't authorized.

## Before starting

The local checkout must be on the PR's head branch and up to date. A dirty
tree with unrelated changes is an immediate escalation: don't stash it.

Keep `WATCH.md` (local and git-excluded, like `PROJECT.md`). Write it freeform,
but make it enough to resume from alone:
- the PR;
- the green target;
- the iteration count;
- the green streak;
- the flaky-reset count;
- reruns used per run ID;
- the newest processed comment;
- escalations.

## Each iteration

Read CI from the PR's `statusCheckRollup` for the head SHA. It includes
external status contexts such as Jenkins, which `gh run list` never shows.
Then read the comments that arrived since the last one processed. Route each
change:

- **Transient Actions failure:** `gh run rerun <run-id> --failed`, at most
  twice per run ID; after that, treat it as real. An external status context
  can't be rerun from here: report a transient one and wait, or escalate.
- **Failure this PR caused:** fix it as `fix-ci` would, verify, push, and
  reset the streak. A fix that needs a rebase or force-push goes to the user
  instead.
- **Failure that predates the PR:** record the evidence and leave it alone.
- **Bot or unambiguous feedback:** handle it per `address-feedback`. Unless
  `--no-comments` was passed, keep replies to humans factual ("Done in
  `<sha>`").
- **Ambiguous, architectural, cross-cutting or conflicting work:** escalate
  without guessing or posting.

Between checks, wait with a background or scheduled wait when the harness has
one. Tell the user when an iteration changed something (a fix, a rerun, a
reply, an escalation); idle iterations stay silent. Keep iterating between
stops instead of ending the turn with a plan or a question.

## Stops

- **Stable:** the green streak reaches its target, no comments are
  unprocessed, and nothing is escalated. An iteration is green only when every
  rollup entry for the head SHA, Actions and external, has passed. The target
  is 1 green, raised to 5 after any flaky or transient failure, unless the
  user set `--greens`.
- **Escalated:**
  - a failure group survives two fixes;
  - a history rewrite or conflict resolution is needed;
  - a human decision is needed;
  - three distinct flaky resets have happened;
  - unrelated dirty work turns up;
  - twelve cumulative iterations pass without stability.

  Repeated flaky failures go to infrastructure, not to more test hardening.

End with what was pushed (with SHAs), reruns used, the final streak, comments
fixed, rebutted and escalated, and anything that needs the user.

## Where it can run

The GitHub API for Preset's private repositories (`superset-shell`,
`superset-private`, `manager`) is reachable only from the corporate VPN.
Jenkins mirrors its build status onto those PRs as commit statuses, and
reading them also needs VPN access.

A cloud-scheduled or cloud-executed watch therefore cannot read these repos.
Run it locally on a VPN-connected machine, in-session or through a local
scheduler. Such a runner fires only while the machine is awake and on the VPN,
so report missed runs rather than implying coverage. Public repositories,
including ai-toolkit, can use cloud scheduling.
