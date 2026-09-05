# End-to-End Bug Workflow

> **When**: A bug report, broken behavior, regression, or error to fix.
> **Produces**: Persisted classification, an evidenced RCA that passed its gate, a regression test, a verified fix, one independent review, QA when relevant, and a summary.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `fix-bug` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record, and `bin/aitk project-state` for the routing
snapshot and gates.

## Usage

```bash
fix-bug "saving settings fails on Safari"
fix-bug sc-12345 | apache/superset#28456 | <github or shortcut url>
fix-bug <report> --watch    # chain into watch-pr after the fix push lands
```

## Bug Complexity Signals

Workflow-specific signals for `rules/complexity-gate.md`; any hard signal there
still forces COMPLEX.

| Signal | TRIVIAL | STANDARD | COMPLEX |
|--------|---------|----------|---------|
| Root cause | Obvious from the error or diff | Confirmed by focused investigation | Unknown, or competing causes still live |
| Files touched | 1-2 | 2-4, one subsystem | 3+ across systems, or unclear ownership |
| Regression risk | Mechanical, local | Contained functional fix | Cross-cutting workflow, data, auth, or migration risk |
| Repro and validation | Cheap targeted check | Targeted test or local repro | Needs RCA validation, an app flow, or broad scenario validation |

STANDARD is the default for a real but contained fix. COMPLEX means the RCA
specialist grades the root cause and the fix plan is validated before code.

## Goal Loop

1. **Intake.** Normalize input, fetch ticket context, restate the symptom in
   code-level terms with a first look at the code path.
2. **Classify** complexity, size, and shape (`rules/complexity-gate.md`) and
   persist: `bin/aitk project-state init --workflow fix-bug ...`. Emit the
   Complexity Gate. Unknown or competing root causes are COMPLEX.
3. **Existing fix.** Run `debug/references/check-existing-fix.md` unless the fix
   is TRIVIAL mechanical work. `FIXED_UPSTREAM` routes to `$cherry-pick`;
   `FIX_PENDING_PR` stops with adopt, monitor, or supersede choices.
4. **Investigate** with `debug/references/investigate-change.md`: inline for
   STANDARD when logs are small, otherwise in the toolkit's debugger agent so
   raw logs stay out of the parent. Reproduce when practical
   (`qa/references/triage-bug.md` when the report is weak).
5. **RCA gate** (`debug/references/review-rca.md`). STANDARD: the parent
   grades the evidence checklist. COMPLEX, confidence below 8/10, or a prior
   failed attempt: the independent RCA specialist grades it. `PASS` records the
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
   plus targeted tests plus repo checks. Two failed implementation attempts, or
   an RCA that materially changed, reopen the RCA gate (rabbit-hole guardrail).
9. **Review** through `review-code` (`review/references/local-review.md`): one
   independent review, validate findings, fix, delta pass if substantive.
10. **Validate** user-visible behavior with `qa/references/validate-fix.md`
    when the app runs; otherwise record why not.
    For BATCHED or MULTI_PHASE fixes, per-unit reviews in step 9 use the phase
    base, and after the last unit's `## Phase Complete` run one **integrated
    review**: a `review-code` pass over the full recorded branch base to HEAD
    plus end-to-end validation against the decomposition's exit goals and
    invariants, with its own `## Gate: review (integrated)` block and Review
    Record entry. It is a hard gate before `## Bug Fix Complete`.
11. **Finish.** Write `## Bug Fix Complete`, emit
    `reporting/templates/fix-bug-summary.md`, record `metrics-emit`. Default
    action when verification is `PASS` at `STRONG` strength (the regression
    test and targeted tests ran locally; `PASS (downstream: CI)` is `PARTIAL`
    and pauses), a regression test was added or the gap explicitly accepted,
    the review gate is `PASS`, and the target is the current feature branch on
    the expected remote: create a new commit and push it. Pause for amend,
    rebase, force-push, an ambiguous push target, `PARTIAL` or `WEAK`
    verification, or any COMPLEX-path hold. With `--watch`, chain into
    `watch-pr` once the push lands on a branch with an open PR.

## User Intervention Points

Only a real product-behavior choice, evidence that depends on a fact or
environment only the user holds, or a safety or effect boundary.

## Hard Gates

- Classification persisted before investigation or implementation.
- RCA gate `PASS` before any COMPLEX fix plan; a bug fix is never `PASS` at
  verification on inspection alone.
- No commit without an added or updated regression test unless the gap is
  explicitly accepted by the user; no auto-push below `STRONG` verification.
- BATCHED or MULTI_PHASE fixes write the `## Phase Complete` block from
  `reporting/templates/phase-handoff.md` before the next unit, and pass the
  integrated review gate before `## Bug Fix Complete`.
- `PROJECT.md` entries at every gate; `## Bug Fix Complete` before the chat
  summary.

```markdown
## Bug Fix Complete
Bug: <one line or ticket>
Complexity/Size/Shape: <from snapshot>
Root cause: <one line> (RCA gate: <parent | specialist>, confidence <n>/10)
Files changed: <list>
Regression test: <added | updated | accepted gap: reason>
Verification: <PASS evidence>
Review: <lane, accepted/raised findings>
Integrated review: <gate, lane | not applicable (SINGLE_PHASE)>
QA: <pass | fail | skipped — reason>
Residual risk: <one line or none>
Commit: <SHA or "no commit">
```
