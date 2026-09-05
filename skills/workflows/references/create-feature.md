# End-to-End Feature Workflow

> **When**: A feature request or planned non-bug work ("add X", "support Y").
> **Produces**: Classified and persisted routing state, a plan sized to the work, verified implementation, one independent review, QA when relevant, and a handoff before the final PR action.

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `create-feature`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record, and `bin/aitk project-state` for the
routing snapshot and gates.

## Usage

```bash
create-feature "add bulk edit for dashboard filters"
create-feature sc-12345 | apache/superset#28456 | <github or shortcut url>
create-feature <request> --watch    # chain into watch-pr after the final push
```

## Goal Loop

The parent (Sonnet or Sol) runs this loop inline. Each step reads the routing
snapshot, evaluates the gate, and either advances or applies `rules/gates.md`.

1. **Intake.** Normalize input (`rules/input-detection.md`), fetch ticket
   context, and inspect the codebase enough to classify without guessing.
2. **Classify** complexity, size, and shape (`rules/complexity-gate.md`) and
   persist it: `bin/aitk project-state init --workflow create-feature ...`.
   Emit the Complexity Gate block. Existing-pattern features are STANDARD.
3. **Scope** only when it is ambiguous: load `pm/references/create-feature-brief.md`
   for a loose request, multiple product surfaces, or unclear acceptance
   criteria. Otherwise the ticket is the brief.
4. **Plan** to the shape:
   - TRIVIAL: no plan; implement.
   - STANDARD, SINGLE_PHASE or BATCHED: compact inline plan
     (`planning/references/plan-implementation.md`) as `PROJECT.md` action
     items; no validation round unless the snapshot's classification
     confidence is `LOW` or the user asked (`validate-plan.md`, When).
   - COMPLEX, SINGLE_PHASE: planner in `phase-plan` mode, then
     `planning/references/validate-plan.md`.
   - MULTI_PHASE: `planning/references/decompose-work.md`, validate the
     decomposition (always, any complexity), then per phase: reclassify the phase,
     `planning/references/plan-phase.md`, validate only if the phase is
     COMPLEX.
   <!-- aitk-model-route:workflows.create-feature-planning -->
   For COMPLEX plans, launch one fresh planner worker on `planning`
   (the toolkit's planner agent, or the routed `planning` specialist) with the
   brief, the routing snapshot line, accepted invariants, and the mode. The
   parent writes the returned plan to `PLAN.md`; the planner never edits files.
5. **Implement** the next unit.
   <!-- aitk-model-route:workflows.create-feature-implementation -->
   Launch one fresh implementer worker on `implementation` (the toolkit's
   implementer agent) for a substantial unit, with the accepted slice, scope,
   exit criteria, and acceptance command (the input block in
   `reporting/templates/phase-handoff.md`); it returns the compact handoff and
   never commits. TRIVIAL and small STANDARD units are implemented inline.
   Parallel workers only for disjoint BATCHED waves or independent slices.
6. **Verify** with `skills/verification-loop/SKILL.md` on the unit. `RETRY`
   stays with the current owner; `ESCALATE` after two attempts reclassifies or
   returns to planning with a compact adjudication package.
7. **Review** through `review-code` (`review/references/local-review.md`):
   one independent review, validate findings, fix, delta pass if substantive.
   Run it after each verified unit for MULTI_PHASE and BATCHED work, once for
   SINGLE_PHASE.
8. **Validate behavior** with `qa/references/validate-feature.md` when
   user-visible behavior changed and the app runs; otherwise record why not.
9. **Checkpoint the unit.** Hard gate before the next unit or any handoff:
   append the `## Phase Complete: <phase or wave>` block from
   `reporting/templates/phase-handoff.md` to `PROJECT.md` (exit criteria met
   with evidence, learned constraints, invariant changes, evidence pointer,
   next phase), mark the phase `done` in the snapshot, and loop to step 4 for
   the next phase. Fresh workers are the context boundary; no manual clear is
   needed.
10. **Finish.** Write the `## Feature Complete` entry, emit the summary from
    `reporting/templates/create-feature-summary.md`, record `metrics-emit`.
    Stop before commit and PR unless authorized; with `--watch`, chain into
    `watch-pr` after the final push lands.

## User Intervention Points

Only an unresolved product, UX, or compatibility trade-off; a fact only the user
holds; a `BLOCKED` environment; or the publish authorization boundary. Ordinary
plan-validation findings and review findings are handled in the loop.

## Hard Gates

- Emit the Complexity Gate before planning or implementing; persist it.
- No implementation of a COMPLEX unit before its plan validates `APPROVE`.
- Verification `PASS` before review; review gate `PASS` before the next unit.
- `## Phase Complete` in `PROJECT.md` before every phase or wave transition;
  `## Feature Complete` before the chat summary.
- Commit or push only with STRONG verification, a `PASS` review gate, and prior
  authorization.

```markdown
## Feature Complete
Feature: <one line or ticket>
Complexity/Size/Shape: <from snapshot>
Phases delivered: <count or single-shot>
Files changed: <summary>
Tests: <added/updated>
Verification: <PASS evidence>
Review: <lane, accepted/raised findings>
Behavior validation: <pass | fail | skipped — reason>
Residual risk: <one line or none>
PR: <URL or "no PR yet">
```
