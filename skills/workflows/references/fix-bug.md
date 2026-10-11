# End-to-End Bug Workflow

> **When**: A bug report, broken behavior, regression, or error to fix.
> **Produces**: Persisted classification, an evidenced RCA that passed its gate, a regression test, a verified fix, one independent review, QA when relevant, and a summary.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

`fix-bug` in `interfaces/contracts.json`; transitions and effects go through
`bin/aitk checkpoint`, the routing snapshot and gates through
`bin/aitk project-state`.

## Usage

```bash
fix-bug "saving settings fails on Safari"
fix-bug sc-12345 | apache/superset#28456 | <github or shortcut url>
fix-bug <report> --no-pr    # commit and push only; skip the draft PR
fix-bug <report> --watch    # chain into watch-pr once the PR exists
```

## Bug Complexity Signals

Workflow-specific signals for `rules/complexity-gate.md`, the one complexity
definition; any hard signal there still forces COMPLEX.

| Signal | TRIVIAL | STANDARD | COMPLEX |
|--------|---------|----------|---------|
| Root cause | Obvious from the error or diff | Confirmed by focused investigation | Unknown, or competing causes still live |
| Ownership | One clear owner | One subsystem, clear owner | Unclear ownership, or crosses a public contract |
| Regression risk | Mechanical, local | Contained functional fix | Cross-cutting workflow, data, auth, or migration risk |
| Repro and validation | Cheap targeted check | Targeted test or local repro | Needs RCA validation, an app flow, or broad scenario validation |

STANDARD is the default for a real but contained fix. COMPLEX means the RCA
specialist grades the root cause and the fix plan is validated before code.

## Goal Loop

1. **Intake.** Normalize input, fetch ticket context, restate the symptom in
   code-level terms with a first look at the code path.
2. **Classify** complexity, size, and shape (`rules/complexity-gate.md`) and
   persist: `bin/aitk project-state init --workflow fix-bug ... --format
   block`, and paste the Complexity Gate it prints. Unknown or competing root
   causes are COMPLEX.
3. **Existing fix.** Run `debug/references/check-existing-fix.md` unless the fix
   is TRIVIAL mechanical work. `FIXED_UPSTREAM` routes to `$cherry-pick`;
   `FIX_PENDING_PR` stops with adopt, monitor, or supersede choices.
4. **Investigate** with `debug/references/investigate-change.md`: inline for
   STANDARD when logs are small, otherwise in the toolkit's debugger agent so
   raw logs stay out of the parent. Reproduce when practical
   (`qa/references/triage-bug.md` when the report is weak).
5. **RCA gate** (`debug/references/review-rca.md`). STANDARD: the parent
   grades the PASS list. COMPLEX work, or an RCA not reproduced, alternatives
   not ruled out, or a prior failed attempt: the independent RCA specialist
   grades it. `PASS` records the
   root cause and regression check in `PROJECT.md`; `REVISE` closes the named
   gaps once; `ESCALATE` moves to `deep-rca` then `USER_DECISION`. Every step
   is one `project-state gate --gate rca --unit rca` record; the runtime climbs
   the ladder and resets the budget per owner.
6. **Plan the fix.** STANDARD: the fix approach and regression test as
   `PROJECT.md` action items. COMPLEX: `planning/references/plan-implementation.md`
   as `PLAN.md`, then `planning/references/validate-plan.md` in `fix-plan`
   mode.
7. **Implement** test-first: write the regression test, watch it fail, fix,
   watch it pass.
   <!-- aitk-model-route:workflows.fix-bug-implementation -->
   Launch one fresh implementer worker on `implementation` (the toolkit's
   implementer agent) for a fix that touches several files or needs a noisy
   test cycle, with the accepted RCA, regression expectation, scope, and
   acceptance command; it returns the compact handoff and never commits.
   TRIVIAL and contained STANDARD fixes are implemented inline.
8. **Verify** with `skills/verification-loop/SKILL.md`: the regression test
   plus targeted tests plus repo checks, each through `bin/aitk verify --run`. Two failed implementation attempts, or
   an RCA that materially changed, reopen the RCA gate (rabbit-hole guardrail).
9. **Review** through `review-code` (`review/references/local-review.md`): one
   independent review, validate findings, fix, delta pass if substantive, by
   the tier table in `rules/code-review.md` (a TRIVIAL fix gets no delta;
   BATCHED fixes review the transformation on wave one; MULTI_PHASE fixes pass
   the phase base recorded with `project-state phase --sha`).
10. **Validate** user-visible behavior with `qa/references/validate-fix.md`
    when the app runs; otherwise record why not.
    BATCHED or MULTI_PHASE fixes end, after the last unit's `## Phase
    Complete`, with one integrated review over the recorded branch base and
    its own `## Gate: review (integrated)` block
    (`review/references/local-review.md`, Integrated Review); it is a hard gate
    before `## Bug Fix Complete`.
11. **Finish.** Write `## Bug Fix Complete`, emit
    `reporting/templates/fix-bug-summary.md`, record metrics with `bin/aitk
    metrics emit --workflow fix-bug --status <status>`. Default
    action when verification is `PASS` at `STRONG` strength (the regression
    test and targeted tests ran locally; `PASS (downstream: CI)` is `PARTIAL`
    and pauses), a regression test was added or the gap explicitly accepted,
    the review gate is `PASS`, and the target is the current feature branch on
    the expected remote: deliver before any `project-state advance`, never from
    `main`. Pause for amend, rebase, force-push, an ambiguous push target,
    `PARTIAL` or `WEAK` verification. In order:
    1. `--no-pr`: commit and push per step 2, then stop, recording
       `pushed — awaiting PR request`.
    2. Create a new commit and push it. When the branch
       already has an upstream, require
       `git rev-parse --abbrev-ref "<branch>@{upstream}"` to equal
       `<remote>/<branch>` (the upstream's own remote), else pause (ambiguous
       push target); then push with
       `git push "<remote>" "HEAD:refs/heads/<branch>"` (never a bare `git push`,
       never `-u`). With no upstream, run `git push -u <remote> HEAD` (`<remote>` is
       `branch.<name>.pushRemote`, else `remote.pushDefault`, else `origin`;
       pause on an ambiguous push target).
    3. Run `create-pr --draft [--base <branch>]`. `## PR Exists` records
       `PR #n (existing, draft|ready)` (from its `Draft:` value) with no
       reservation; `## PR Not Opened` records its `pushed — awaiting PR request
       (<reason>)` line.
    4. On `## PR Ready`, run `bin/aitk checkpoint reserve --workflow fix-bug
       --key published_pr --operation-id phase:<name>` (`phase:single` for a
       SINGLE_PHASE fix), resume `create-pr` at its step 7, then `bin/aitk
       checkpoint apply --workflow fix-bug --key published_pr --operation-id
       phase:<name> --result-digest sha256:<sha256 of the PR URL>`, and finish
       `create-pr` steps 8-9.

    The PR is a draft only; promotion, reviewers, and merge need the user's
    words. With `--watch`, chain into `watch-pr` once the PR exists.

## User Intervention Points

Only a real product-behavior choice, evidence that depends on a fact or
environment only the user holds, or a safety or effect boundary.

## Hard Gates

- Classification persisted before investigation or implementation.
- RCA gate `PASS` before any COMPLEX fix plan; a bug fix is never `PASS` at
  verification on inspection alone: the verification gate counts only with a
  `bin/aitk verify --run` record of the regression command exiting 0.
- No commit without an added or updated regression test unless the gap is
  explicitly accepted by the user; no auto-push below `STRONG` verification.
- BATCHED or MULTI_PHASE fixes write the `## Phase Complete` block from
  `reporting/templates/phase-handoff.md` before the next unit, and pass the
  integrated review gate before `## Bug Fix Complete`.
- `PROJECT.md` entries at every gate; `## Bug Fix Complete` before the chat
  summary.

`## Bug Fix Complete` in `PROJECT.md` carries the fields the summary
(`reporting/templates/fix-bug-summary.md`) does not:

```markdown
## Bug Fix Complete
Bug: <one line or ticket>
Complexity/Size/Shape: <from snapshot>
RCA gate: <parent | specialist>
Regression test: <added | updated | accepted gap: reason>
Verification: <PASS evidence>
Integrated review: <gate, lane | not applicable (SINGLE_PHASE)>
QA: <pass | fail | skipped — reason>
Commit: <SHA or "no commit">
```
