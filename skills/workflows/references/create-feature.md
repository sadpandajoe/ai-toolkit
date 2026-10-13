# End-to-End Feature Workflow

> **When**: A feature request or planned non-bug work ("add X", "support Y").
> **Produces**: Classified and persisted routing state, a plan sized to the work, verified implementation, one independent review per unit and one integrated review for phased work, QA when relevant, and a handoff before the final PR action.

## Effect Boundary

Effect: `git_mutation`.

## Usage

```bash
create-feature "add bulk edit for dashboard filters"
create-feature sc-12345 | apache/superset#28456 | <github or shortcut url>
create-feature <request> --no-pr              # commit and push only; skip the draft PR
create-feature <request> --watch              # chain into watch-pr once the PR exists
create-feature <request> --deliver-per-phase  # separate branch + draft PR per phase; no-op alias on one branch
```

## Feature Complexity Signals

Workflow-specific signals for `rules/complexity-gate.md`, the one complexity
definition; any hard signal there still forces COMPLEX.

| Signal | TRIVIAL | STANDARD | COMPLEX |
|--------|---------|----------|---------|
| Design decision | None; an existing pattern applied | One known pattern, bounded choices | Several plausible designs, or a new pattern |
| Ownership | One clear owner | One subsystem, clear owner | Unclear ownership, or crosses a public contract |
| Behavioral change | Cosmetic: theme, copy, spacing, a button type or variant | Contained new behavior | Cross-cutting behavior or a contract change |
| Risk | Local, reversible | Contained functional risk | Data, auth, migration, compatibility, or cross-service risk |

Cosmetic changes are TRIVIAL regardless of file count unless the impact is
CORE; across many files they are STANDARD or TRIVIAL with shape BATCHED, planned
inline as one transformation and reviewed once on the first wave. STANDARD is
the default for real, contained work.

## Goal Loop

The parent (orchestrating) session runs this loop inline. Each step reads the routing
snapshot, evaluates the gate, and either advances or applies `rules/gates.md`.

1. **Intake.** Normalize input (`rules/input-detection.md`), fetch ticket
   context, and inspect the codebase enough to classify without guessing.
2. **Classify** complexity, size, and shape (`rules/complexity-gate.md`) and
   persist it: `bin/aitk project-state init --workflow create-feature ...
   --format block`, and paste the Complexity Gate block it prints.
   Existing-pattern features are STANDARD.
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
     plan it (`planning/references/plan-implementation.md`), validate only if
     the phase is COMPLEX.
   <!-- aitk-model-route:workflows.create-feature-planning -->
   For COMPLEX plans, launch one fresh planner worker on `planning`
   (the toolkit's planner agent, or the routed `planning` specialist) with the
   brief, the routing snapshot line, accepted invariants, and the mode. The
   planner never edits files: it returns the `PLAN.md` section, and for a
   decomposition its fenced `phases-json` block. The parent writes the section
   to `PLAN.md` verbatim and passes the block unchanged to
   `bin/aitk project-state phases --phases-json`.
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
   Run it after each verified phase for MULTI_PHASE work, once for
   SINGLE_PHASE. BATCHED work reviews the transformation: a full review of the
   first wave, verification-only for later identical waves, and its own lane
   only for a wave that deviates. Per-unit reviews pass the **phase base** (the
   `tree` SHA the previous phase recorded in the snapshot), so a phase-three
   review measures only phase three; the branch base is reserved for the
   integrated review in step 10. Review depth is what `bin/aitk review plan`
   prints; a TRIVIAL unit gets no delta pass.
8. **Validate behavior** with `qa/references/validate.md` when
   user-visible behavior changed and the app runs; otherwise record why not.
9. **Checkpoint the unit.** Hard gate before the next unit or any handoff:
   append the `## Phase Complete: <phase or wave>` block from
   `reporting/templates/phase-handoff.md` to `PROJECT.md` (exit criteria met
   with evidence, learned constraints, invariant changes, evidence pointer,
   roadmap check, `Tree:`, next phase) and mark the phase `done` in the
   snapshot with `bin/aitk project-state phase --name <phase> --status done
   --sha <tree>`; that SHA is the next phase's review base. The template owns
   the roadmap check: `holds` advances to step 4 for the next phase, and
   anything else records `--gate phase-exit --status RECLASSIFY` and
   revalidates the decomposition before the next phase is planned.
   For MULTI_PHASE work the phase is then delivered as its own commit in the
   roadmap's delivery order (`decompose-work.md`) with step 11's `deliver`
   line, without asking and before the phase is marked advanced. Phases on one
   branch share one draft PR (`deliver` finds it); a phase on a separate
   branch gets its own. With `--no-pr` the phase stays `pushed — awaiting PR
   request` and the loop continues.
10. **Integrated review** (MULTI_PHASE and BATCHED only; hard gate before
    `## Feature Complete`). After the last unit's checkpoint, run one more
    `review-code` pass over the recorded **branch base** to HEAD, with its own
    `## Gate: review (integrated)` block, as `review/references/local-review.md`
    (Integrated Review) defines it.
11. **Finish.** Deliver after the review gate is `PASS` and before any
    `project-state advance`: draft the title and body with `create-pr` steps
    2-5, then run `bin/aitk deliver --workflow create-feature --phase <name>
    --title "<title>" --body-file <file> [--no-pr]` and paste the block it
    prints. It commits, pushes and opens or reuses the draft PR only on the
    recorded review and verification run, never from the default branch; a
    refusal names the missing gate, and a hold (`## PR Not Opened`) is
    recorded as printed. Then write the `## Feature Complete` entry, emit the
    summary from `reporting/templates/create-feature-summary.md`, and record
    metrics with `bin/aitk metrics emit --workflow create-feature --status
    <status>`.

    The PR is a draft only: promotion to ready for review, reviewers, and merge
    need the user's explicit words, and a non-draft PR needs them too. With
    `--watch`, chain into `watch-pr` once the PR exists.

## User Intervention Points

Only an unresolved product, UX, or compatibility trade-off; a fact only the user
holds; a `BLOCKED` environment; or promoting a draft PR (ready for review, reviewers, merge). Ordinary
plan-validation findings and review findings are handled in the loop.

## Hard Gates

- No implementation of a COMPLEX unit before its plan validates `APPROVE`.
- MULTI_PHASE and BATCHED work: integrated review gate `PASS` over the branch
  base before `## Feature Complete`.

Delivery is the contract's `publish-explicit` gate, satisfied by
`bin/aitk deliver`, which opens drafts only.

`## Feature Complete` in `PROJECT.md` carries the fields the summary
(`reporting/templates/create-feature-summary.md`) does not:

```markdown
## Feature Complete
Feature: <one line or ticket>
Complexity/Size/Shape: <from snapshot>
Phases delivered: <count or single-shot>
Tests: <added/updated>
Verification: <PASS evidence>
Behavior validation: <pass | fail | skipped — reason>
Integrated review: <gate, lane, accepted/raised | not applicable (SINGLE_PHASE)>
```
