---
name: test-pr
description: Test a PR, a test-plan doc, a feature area, or a Shortcut story in a running app (a local Superset stack or a Preset staging or dev workspace), capture screenshot and video evidence including before/after for UI changes, and report results. Use for manual or browser verification, running a test plan, or producing UI evidence for a PR. Do NOT use for writing automated tests, root-cause investigation, code review, or anything against production.
---

# Test PR

Verify user-visible behavior in a running app and report what happened, with
evidence. This skill validates; it does not change product code or file bugs.

## Inputs

- A PR (`123`, `owner/repo#123`, a URL): `gh pr view <ref> --json
  number,title,body,baseRefName,headRefName,files` and `gh pr diff <ref>`;
  translate the author's "how to test" notes into scenarios.
- A test-plan doc, a feature area, or a Shortcut story (`sc-12345`, fetched
  with the `shortcut` skill).
- Check out the PR branch only when asked (`gh pr checkout <n>`); then the
  user restarts the app before you continue.

## Environment

The app must already be running; this skill does not start dev servers. Use
the URL you were given, otherwise probe `localhost` on 3000, 4000, 5000, 8000,
8080, 8088, 9000 and 9001 and the host ports in `docker ps`. One hit: use it
and say so. Several: ask which. None: ask the user to start the app (for
Superset, the `superset-local` skill starts the stack and prints the frontend
URL).

Classify the host and pick credentials with
[references/preset-environments.md](references/preset-environments.md).
Production and unknown hosts are refused: no browser automation against them,
and the scripts refuse them too.

## Scenarios

Scale the count to how critical the touched behavior is: about 3 for
low-exposure changes (admin and debug tooling, docs, fixtures, CI config), 4–5
for regular features (filters, settings, exports, search), 6–7 when a core
flow is touched, with guards on adjacent core flows. "Smoke" caps it at 3.

Core flows in Preset and Superset: Manager login and SSO, RBAC/DAR/RLS
checks, dashboard and chart render, SQL Lab execution, embedded auth.

Tag each scenario `[new]` (behavior the PR adds), `[fix]` (the bug it claims
to fix, describing the broken state), or `[guard]` (the most-traveled
adjacent path that could regress), with steps and an exact pass condition.
Print the list and proceed; invoking this skill delegates scenario selection
on local, staging and dev. Pause for edits only when the user asked to step
through.

## Run

Dispatch the scenarios to the `qa-runner` agent so browser output stays out
of this session. Its brief carries the toolkit root, the app URL, the role,
the source id (`pr-NNNN`, `sc-NNNNN`), the scenarios, and the full text of
[references/browser-recording.md](references/browser-recording.md). For a UI
change, ask for **before** (the base branch, or the environment without the
change) and **after** (the PR) on the same scenarios; those are the PR's
before/after evidence. Before needs the app running the base: capture it
before the change is applied, or ask the user to switch the stack. Scenarios run sequentially in one recording; a failure
is captured and the run moves on, with no retry until after the report.

## Resources

Before anything starts a stack or a large test run, check capacity as the
`superset-local` skill describes. Cap test workers explicitly (Jest
`--maxWorkers`, pytest `-n`); keep `playwright.config`'s workers.

## Report

Show the results in the terminal with each scenario's result, evidence paths,
and the recording path. Post only when asked: the body follows
[references/qa-report-format.md](references/qa-report-format.md); Shortcut
uploads and comments go through the `shortcut` skill; a PR comment uses
`gh pr comment <pr> --body-file <path>`. `gh` cannot attach files, so give the
user the media paths to drag into the PR, with the recording transcoded under
GitHub's attachment limit (see the recording reference).

For existing Superset Playwright specs, use the `superset-local` skill
instead.
