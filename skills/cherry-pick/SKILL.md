---
name: cherry-pick
description: Cherry-pick, backport, or apply commits or PRs onto another branch, one at a time or in batches, with a scope-leak audit and validation per cherry; also release audits ("what's on master that hasn't reached the release branch?", backport candidates). Use when moving existing commits between branches. Do NOT use for same-branch bug fixes, broad refactors, dependency upgrades, or rewriting behavior.
---

# Cherry-Pick

Move isolated changes (bug fixes, isolated features) onto a target branch
without leaking neighbouring commits. Read [gotchas.md](gotchas.md) before
adapting a conflict or reporting a blocked row: every entry is a past incident.

```
cherry-pick <pr-url | sha>... [--target <branch>] [--force] [--plan-only] [--no-push] [--step]
```

`--force` overrides a reject-category verdict only; it skips no audit or
validation. `--plan-only` stops before applying. `--step` pauses at each
default decision.

## What invoking it authorizes

For the run: the cherry-pick commits on `--target`, amending the in-progress
(unpushed) cherry with validation fixes, and a fast-forward `git push` of each
validated cherry. Not force-push, rebase, amending a pushed commit, pushing
another branch, or opening or merging a PR. `--no-push` withdraws the push.

## Org data

The release-candidate label id and the upstream repository live in the target
repo's `.ai-toolkit/config.json` as `cherry_pick.release_candidate_label_id`
and `cherry_pick.upstream_repo` (`owner/name`). When a key is missing, ask once
and write it there.

## Deciding whether to pick

| Accept | Reject (needs `--force`) |
|--------|--------------------------|
| Bug fixes, isolated features, algorithm improvements, tests, docs | Architecture changes, unverified imports, breaking API changes, build-system changes, file restructuring |

An ambiguous category counts as reject. With `--force`, carry the overridden
criteria into the final report.

- **Already fixed?** Search the source branch, the target branch and merged
  PRs, never `git log --all`: unmerged branches hold code that never shipped.
  A fix still in an open PR on master is not on the release branch; backport
  it and note the PR.
- **Not affected** needs concrete evidence: an introducing commit that `git
  merge-base --is-ancestor` shows is absent from the target, or the buggy path
  demonstrably absent. When unsure, pick and record the open question. A false
  "not affected" silently drops a real fix; a false "affected" is caught by an
  empty pick or the audit. A live bug whose fix won't apply ends `Blocked` or
  `Partial`, never `Skipped`.

## Per cherry

1. Apply with `git cherry-pick -x`: [references/apply.md](references/apply.md).
2. Scope-audit **every** cherry, clean applies included, then validate:
   [references/validate.md](references/validate.md).
3. Push each cherry as soon as it validates, before the next one's work
   ([gotchas.md](gotchas.md) #5). Batch pushes only when the user asks; a
   dependent cherry waits until the previous one is pushed.
4. Blocked or rejected because the target lacks something: name what would
   unstick it ([references/unblock-discovery.md](references/unblock-discovery.md)).
   For a release-candidate story that did not land, notify the labeler
   ([references/blocked-owner-comment.md](references/blocked-owner-comment.md)).

Several PRs or SHAs: [references/batch.md](references/batch.md). "What hasn't
reached the release branch?": [references/release-audit.md](references/release-audit.md)
first; it yields candidates, not a cherry list.

## Run notes and report

Keep `CHERRY_PICK.md` (local, never committed) current on long or batch runs
so a fresh session resumes from its active row. Its row vocabulary and the
final summary format are in [references/run-notes.md](references/run-notes.md).
