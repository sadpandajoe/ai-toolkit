---
name: fix-ci
description: Diagnose and fix failing CI on a PR or branch — enumerate every failing check including external CI such as Jenkins, classify each failure, fix what the change broke, verify locally, and push. Use when a CI run, PR check or build fails (a run URL, a PR number, a log file or zip, or the current branch). Do NOT use for bugs found outside CI (use fix-bug) or for watching a PR until it is green (use watch-pr).
---

# Fix CI

## Evidence

A CI signal is a summary, and the evidence is the log behind it. Three
summaries are confidently wrong:

| Summary | What it hides | Open instead |
|---|---|---|
| `gh run list`, `gh pr checks` | External CI (Jenkins, Buildkite, CircleCI) posts commit statuses, not Actions. One noisy Actions failure makes a red PR look explained. | `gh pr view <n> --json statusCheckRollup` (CheckRun **and** StatusContext) |
| A check's description | Pipelines post one generic string for every failure; "cannot be built" can be a broken test. | The console log |
| A green check | It proves only what it asserts. A green migration-conflict check means no filename collision, not a single Alembic head; 4038 tests failed on a PR that looked clean. | The thing the check didn't assert |

Count every rollup entry in `failure`, `error`, `cancelled` or `timed_out`.
Only an empty merged list means there are no failures. When a log is
unreachable (an auth wall, a dead `targetUrl`), ask the user for an excerpt;
never reason from the status name.

## Investigate

Send log gathering and classification to the `ci-investigator` agent, so raw
logs stay out of this session. Use one agent per independent failure when
there are several; each returns one record per failure. Read the logs yourself
only for a single short failure.

A failure is ours only if both hold:
- the failing file or test is in our diff;
- the base branch's full rollup doesn't fail the same way.

With three or more failed jobs, or artifact bundles, keep `CI_FIX.md` (local
notes) with the sources, log paths, root-cause groups and fix status.

## Fix

- **Not ours.** When every failure is pre-existing or transient, report the
  evidence and stop. There is nothing to fix.
- **Transient infra.** A 5xx or timeout in checkout, auth, artifact transfer or
  runner setup: run `gh run rerun <id> --failed`, at most twice, then treat it
  as real.
- **401 vs 403.** A **401** on a step that normally authenticates is a token
  blip, so rerun it. A **403** with a stable identity is a real permissions
  problem. Never ship a permissions fix for a 401.
- **OOM.** Exit 137, `Killed` or `JavaScript heap out of memory` is a resource
  problem, not code. Lower the worker count or raise the job's memory before
  touching tests. Jest's default worker count can OOM, so pass `--maxWorkers`;
  size pytest `-n` the same way.
- **Flaky tests.** After two independent test-layer hardenings (retries,
  warm-up gates, polling) miss the same flake family, stop patching tests and
  look at infrastructure: OOMKills, pod restarts, resource limits, host-daemon
  contention (buildx builds run outside the pods' cgroups), or a warm-up that
  succeeds while the workspace degrades mid-run. One PR stacked four retry
  layers against a pod that was OOMKilled every two minutes; a one-line helm
  memory bump (1200Mi→3Gi) fixed it.
- **Cherry-pick residue.** Conflict markers (`<<<<<<<`) committed in files.

## Verify and push

Push only after the local command closest to the failing CI step passes.
When the failing check can't run locally, present the fix and ask before
pushing, so CI can verify it.

A new commit is the default; amending needs the user's go-ahead. On a cherry-pick branch
(`git log --grep="cherry picked from commit"`), the amend target is the picked
commit that last touched the failing files, not necessarily the tip:

```bash
git commit --fixup=<sha>
git rebase --autosquash <base>
```

The rebase rewrites pushed history, so the push needs `--force-with-lease`
and the user's go-ahead.

Commit fixups in dependency order. Pre-commit stashes unstaged changes while it
checks a fixup, so a later commit's fix disappears from the checked tree.

If the fix needs a new branch, open its draft PR with the `create-pr` skill.
