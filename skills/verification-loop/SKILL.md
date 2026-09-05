---
name: verification-loop
description: Use when a goal workflow needs to run its required checks, decide PASS / RETRY / ESCALATE / RECLASSIFY / USER_DECISION / BLOCKED, and drive fix-and-recheck within the retry budget. Do NOT use as a reviewer, for safety or publish authorization, or before an implementation attempt exists.
---

# Verification Loop

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.
Read and apply `rules/gates.md`.

The shared loop every goal workflow chains after an implementation attempt, a
fix, or a plan. It owns iterative verify, fix, and recheck behavior so no
workflow carries its own gate machinery. The parent runs it inline; when the
checks are noisy, the parent may run the check-and-summarize step in a fresh
worker and grade the handoff here.

## Inputs

- The unit under verification: slice, fix, phase, or plan name (the attempt
  budget is charged to it).
- Required checks: the acceptance command from the plan or RCA, plus targeted
  tests for changed files, plus build, lint, and typecheck when the repo has
  them. For plans, the required check is the plan validator's verdict.
- Optional conditional checks: user-visible validation when behavior changed
  and the app runs; a downstream verifier (CI) when local execution is
  impossible.

## Loop

1. **Run the required checks.** Quote commands and results in one line each.
2. **Grade.**
   - All required checks ran locally and pass → `PASS` at `STRONG`. Record
     it: `bin/aitk project-state gate --gate verification --status PASS`.
   - A check fails and the current owner can plausibly fix it → attempt the
     fix, then record `--status RETRY --unit <unit>` (add `--same-failure` when
     the reason repeats). The runtime returns `RETRY` or `ESCALATE`; obey it.
   - `ESCALATE` → stop fixing. For implementation failures, reclassify upward
     if a hard signal appeared, otherwise route the unresolved question to the
     RCA specialist (bugs) or the planner (features) with a compact
     adjudication package. Never a third quiet attempt.
   - A check cannot run and no downstream verifier exists → `BLOCKED` with
     what is missing. With a downstream verifier → `PASS (downstream: CI)` at
     `PARTIAL` (related checks ran) or `WEAK` (nothing ran; `fix-ci` and
     `watch-pr` only, and `BLOCKED` under `--gate-strict`). A downstream pass
     continues the workflow but never authorizes a commit or push; the
     no-push-after-failed-verification invariant holds. The strength table is
     in `rules/gates.md`.
   - An editorial fix (a path, wording, a rollback note) is recorded with
     `--editorial` and is not charged.
   - The failure exposes a product or scope choice → `USER_DECISION`.
3. **Recheck after every fix** with the same required set; a fix that passes
   only its own test is not `PASS`.
4. **Emit the gate block** from `rules/gates.md` and hand control back to the
   workflow. The workflow decides what follows; this loop never commits,
   pushes, or reviews.

## Shapes

- **BATCHED work**: verify each wave or item class, then the aggregate state
  once at the end.
- **MULTI_PHASE work**: each phase has distinct exit conditions; a phase does
  not pass on the previous phase's checks.
- **Plans**: the required check is `Verdict: APPROVE` from
  `skills/planning/references/validate-plan.md`; `CHANGES_REQUIRED` is a
  `RETRY` for the planner, `REPLAN` is `ESCALATE`.

## Output

The `## Gate: verification` block with its `Strength` line, followed by a
one-line `Reviewer yield` or `Fix summary` only when fixes were applied.
