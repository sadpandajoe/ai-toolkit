---
name: cherry-pick
description: Cherry-pick, backport, or apply commits/PRs onto another branch with safety gates and per-change validation; also release audits — "what's on master that hasn't reached the release branch", finding backport candidates. Do NOT use for same-branch bug fixes, broad refactors, dependency upgrades, or general behavior rewrites.
---

# Cherry-Pick

Safely move one or more isolated changes (bug fixes, isolated features) onto a
target branch. Recurring failure modes are in [gotchas.md](gotchas.md); read it
before adapting a conflict or reporting a blocked row.

## Contract

**In scope:** classify each change, plan its application, apply, adapt
conflicts when source intent can be preserved, run repo-standard validation.

**Out of scope:** broad refactors, behavior-changing adaptations without
approval, dependency reinstall or environment rebuild, forcing incompatible
APIs onto the target.

**Success criteria:** each change ends `Applied | Partial | Blocked | Rejected
| Skipped`; applied changes preserve source intent; validation and push status
are recorded in its `CHERRY_PICK.md` row. This skill owns PROJECT.md and
CHERRY_PICK.md for its run.

If the workflow would cross a contract boundary, stop and ask; do not cross
first and report after.

## Effect Boundary

Effect: `external_effect`.

## Authorization Boundary

Authorization mode: `invocation`. Invoking cherry-pick authorizes, for the
duration of the run, the cherry-pick commits on `--target` (including the
validation-only amend of the in-progress cherry before it is pushed) and a
fast-forward `git push` of each validated cherry to `--target`. It does not
authorize force-push, rebase, amending a pushed commit, pushing any other
branch, or opening or merging a PR. `--no-push` withdraws the push. The phase
graph and gates are the `cherry-pick` entry in `interfaces/contracts.json`.

## Usage

```
cherry-pick <pr-url>                          # From a PR
cherry-pick <sha>                             # Single commit
cherry-pick <sha> --target <branch>           # Specific target branch
cherry-pick <sha> --force                     # Override reject-category gate
cherry-pick <sha-1> <sha-2> <sha-3>           # Batch
cherry-pick <sha-1> <sha-2> --plan-only       # Plan without applying
cherry-pick <sha-1> <sha-2> --no-push         # Validate locally; stop with push recommendation
cherry-pick <sha-1> <sha-2> --step            # Pause for a decision at each default
```

## Release Audit

For "what's on `<source>` that hasn't reached `<release-branch>`?", run the
audit before building any cherry list:
[references/release-audit.md](references/release-audit.md)
(`scripts/release-audit.sh`). It produces candidates, not decisions; every
queued row still runs the flow below.

## Single Cherry-Pick Flow

Phases run in this order; no validation phase may be skipped, whatever the
difficulty.

| # | Phase | Reference |
|---|-------|-----------|
| 1 | Investigate: source, target compatibility, prerequisites, target-affected scan; raw signals only | [investigate.md](references/investigate.md), [template](assets/investigation-template.md) |
| 2 | Gate: accept/reject, target-affected skip, TRIVIAL vs NON-TRIVIAL; `--force` overrides reject only | [gate.md](references/gate.md) |
| 3 | Plan, on the main thread for both difficulty classes | [plan-template.md](assets/plan-template.md) |
| 4 | Apply: `git cherry-pick -x`, `-m 1` for a merge, `git rm` for modify/delete | [apply.md](references/apply.md) |
| 5 | Adapt (non-trivial, or a trivial pick that hit conflicts): surgical resolution, never `--theirs`/`--ours` | [adapt.md](references/adapt.md) |
| 6 | Validate: scope audit, then pre-commit, build, type-check, targeted tests | [validate.md](references/validate.md) |
| 7 | Unblock discovery (`Blocked` / `Rejected` only) | [unblock-discovery.md](references/unblock-discovery.md) |
| 8 | Blocked-owner notification (release-candidate stories only) | [blocked-owner-comment.md](references/blocked-owner-comment.md) |
| 9 | Per-cherry push | below |

**Scope audit.** The parent runs `<skill-dir>/scripts/scope-audit.sh` on every
cherry, clean applies included; the LLM audit and its route are in
[validate.md](references/validate.md). A cherry is never `Applied` without
the audit result in its row.

**Unblock discovery.** When a cherry ends `Blocked` or `Rejected` because the
target is missing something (modify/delete, a flagged prerequisite, missing
architecture), the parent runs `<skill-dir>/scripts/unblock-measure.sh` on the
candidate PRs it finds.
<!-- aitk-model-route:cherry-pick.unblock-discovery -->
Then spawn one discovery worker on `review` with only that output and the blocker signals, to name and order the upstream PRs that would unstick the row and rate the chain `easy | heavy | risky`.
Skip it when the rejection is intrinsic (reject-category rewrite, dependency
bump, build-system change) and record "no unblock path". The result is
inform-only: candidates go to the final report, and the user decides whether
to add them.

**Blocked-owner notification.** When a release-candidate story's cherry did
not land (`Skipped`, `Blocked` or `Rejected`), the labeler decides; see the
reference. Never notify on `NOT_AFFECTED`, an already-applied merge SHA, or a
story with no merged PR in `cherry_pick.upstream_repo`.

### Per-Cherry Push

Immediately after validation passes for this cherry, and before any later
work (the next cherry's investigate or apply, the final report, a checkpoint,
or a PR), run `git push` and set the row's **Push** cell in `CHERRY_PICK.md`:
`pushed <sha>` once the SHA is on the remote, `pending-authorization` under
`--no-push`, or `deferred` when the user deferred it, with a one-line reason
in Notes when not pushed. Do not start a dependent cherry while the previous
row's Push cell is empty or not `pushed`; independent rows may continue.

Per-cherry push lets CI attribute each cherry on its own; batching forces a
bisection later. Batch pushes only when the user asks (for example, to save
CI); that request is the authorization. Never batch on your own initiative
([gotchas.md](gotchas.md), "Push batched at end").

## Batch Cherry-Pick Flow

For multiple PRs or SHAs, follow [references/batch.md](references/batch.md):
pre-flight, ordering, the manifest, waves, worker handoffs and `--plan-only`.
The single-cherry gates and the per-cherry push still apply to every row.

## Final Report

Use [examples/final-report.md](examples/final-report.md): lead with the ticket
outcome, then the compact table, then actionable residuals. The row schema is
[templates/cherry-pick-manifest.md](templates/cherry-pick-manifest.md).

`bin/aitk metrics emit --workflow cherry-pick --status <clean | blocked>`,
with `--extra complexity=<trivial | non-trivial>`, `--extra 'decisions={"verdict":
"PROCEED | REJECT | FORCE-PROCEED", "batch_size": N}'`, `--extra
'scope_audit={"clean": N, "leaked_reverted": N, "escalated": N}'` and
`--workers <route>=<n>`.

## Notes

- **Org data** (the release-candidate label id, the upstream repository) lives
  in `.ai-toolkit/config.json` in the target repo under `cherry_pick.*`. When
  a key is missing, ask the user once and write it there; `.ai-toolkit/` stays
  out of commits.
- If the accept/reject category itself is ambiguous, treat it as reject and
  surface `--force`. (`Target-affected: UNCLEAR` still proceeds.)
- For a long or batch run, keep `CHERRY_PICK.md` current so a fresh session
  resumes from its active row or wave.
