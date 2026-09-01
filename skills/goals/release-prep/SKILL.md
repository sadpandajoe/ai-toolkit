---
name: release-prep
description: Use to check whether a branch is ready to ship — clean working tree, build/artifacts succeed, CI is green — and produce a go/no-go readiness report. Do NOT use to actually publish, tag, merge, or deploy a release (a separate, explicitly authorized action this skill never performs), to discover backport candidates for a release branch (skills/goals/cherry-pick's release audit), or to diagnose one failing CI check outside a release context (skills/goals/fix-ci).
---

# Release Prep

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `release-prep`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Before Starting

Read `rules/gates.md` (six-state gate contract), `rules/durable-workflows.md`,
and `rules/preset-environments.md`'s Network Reachability section (CI/branch
checks against a VPN-restricted repo need the same VPN awareness as
`test-pr`/`run-test-plan`) before continuing. Read the `release-prep` entry
in `interfaces/contracts.json` (durable runtime: effect `local_mutation`,
authorization mode `invocation` with gate `verification`, phases
check-branch→check-artifacts→check-ci→readiness, resumable via `PROJECT.md`)
before continuing.

## Scope

**In scope:** checking whether the current branch (or a named target) is
ready to ship — working tree state, build/artifact success, and CI status —
and reporting a go/no-go readiness verdict with the specific blockers if any.

**Out of scope, by design:** this skill never publishes. Tagging, creating a
release, merging to a protected branch, or deploying is a separate,
explicitly authorized action a human takes after reading this skill's
readiness report — treat it the same as any other irreversible external
effect this toolkit gates on `USER_DECISION`/explicit confirmation, not
something a readiness check performs on its own. Also out of scope:
discovering which commits are missing from a release branch — that's
`skills/goals/cherry-pick`'s release audit (a different question: "what
hasn't reached this branch" vs. this skill's "is what's here ready"); and
diagnosing a single CI failure outside a release context —
`skills/goals/fix-ci`, which this skill dispatches internally when a
release-blocking CI failure needs a fix (see step 3).

## Steps

1. **Check branch.** Identify the release target (a branch name, or the
   current branch by default). Run `git status --porcelain` (clean working
   tree required — a dirty tree is a blocker, not a warning) and `git fetch`
   + compare against the intended base/upstream (unmerged base commits, or
   commits on this branch not yet reachable from where it will ship, are
   evidence for the report, not automatically blockers — flag them and let
   the readiness gate below decide). Confirm the branch is not itself a
   protected branch being prepared against nothing (e.g. preparing `main`
   against `main`).
2. **Check artifacts.** Run this repository's own build/verification step
   (`bin/aitk check` in this repo; the project's own build/lint/test command
   elsewhere) and confirm it succeeds. A missing or unrunnable build step is
   evidence, not a silent pass — record it as a blocker with the reason, not
   as "not applicable".
3. **Check CI.** Check the latest CI run status for the release target (`gh
   pr checks` / `gh run list` or equivalent) against `rules/
   preset-environments.md`'s VPN constraint for Preset repos. A required
   check that is failing or still pending is a blocker. If a release-blocking
   CI failure is itself fixable, dispatch `skills/goals/fix-ci` wholesale
   against it — do not reimplement diagnose/fix/verify here — then re-check
   before continuing; do not treat an in-flight fix as already resolved.
4. **Readiness Gate.** Aggregate steps 1-3 into a single Gate block under
   gate name `release-prep-readiness`, per `rules/gates.md`'s six-state
   contract: `PASS` (clean tree, build/artifacts succeed, CI green — ready to
   ship), `RETRY`/`ESCALATE` per the Repeat-Failure Counting Rule if a check
   itself failed to run cleanly (not the same as the release being
   unready), `BLOCKED` when a required check fails and has no available fix
   path, `USER_DECISION` when readiness depends on a judgment call only the
   user can make (e.g. an unmerged upstream commit that may or may not need
   to land first).
5. **Report.** Record a `## Release Readiness` entry in `PROJECT.md`: the
   Gate outcome, each of the three checks' individual result, and — if not
   `PASS` — the specific blocking items in priority order. State explicitly
   in the report that publishing is a separate action this skill did not
   take and will not take.

## Output

The `release-prep-readiness` Gate block plus the three-check breakdown
(branch, artifacts, CI), and either a `PASS` readiness verdict or the
specific blockers — never a publish action.

## Notes

- Declares no dispatch boundaries of its own — the only dispatch this skill
  makes (step 3's CI-fix path) goes through `skills/goals/fix-ci`'s own
  dispatch boundaries.
- This skill's contract is deliberately `local_mutation`, not
  `external_effect` or `git_mutation` — it never pushes, publishes, or
  writes anything outside `PROJECT.md`. If a future workflow adds an actual
  publish step, that step needs its own `external_effect` contract with
  `authorization.mode: "explicit"` and a `publish-explicit` gate, per
  `rules/gates.md`'s treatment of irreversible external effects — it must
  not be folded into this skill's existing `invocation`-mode authorization.
