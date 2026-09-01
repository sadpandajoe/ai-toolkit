# One-Off Plan Review


> **When**: You have a `PLAN.md` or PROJECT.md-referenced plan and want a quality review without the full `create-feature` workflow.
> **Produces**: Reviewed `PLAN.md`, all applicable reviewers gated `PASS`, cold read passed, and final gate outcomes in PROJECT.md.

## Effect Boundary

Effect: `local_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `review-plan` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Usage

```
review-plan
```

## Required Context

Each reviewer's checkpoint uses `rules/gates.md`'s six-state contract
(`PASS`/`RETRY`/`ESCALATE`/`USER_DECISION`/`BLOCKED`/`RECLASSIFY`), not a
numeric score.

The reviewer lenses themselves are **not** listed here. Both dispatch boundaries
below fan out over the plan-lens menu declared in `interfaces/model-routing.json`,
so each worker receives exactly the one lens its dispatch selected. Listing them
as shared context instead handed every plan reviewer all six sibling contracts and
asked it to review under six conflicting output formats at once.

## Command Contract

This workflow owns one-off plan review only. It does not create the plan,
implement it, or turn review comments into code changes.

- Read PROJECT.md to find the active plan pointer, then review `PLAN.md` as the formal plan body; do not preload unrelated workflow references.
<!-- aitk-model-route:workflows.review-plan-fresh -->
- Use fresh reviewer subagents for each review pass after material plan revisions.
  One dispatch per lens, selected from the plan-lens menu — the same menu step 3
  draws from: [architecture.md](../../review/references/architecture.md),
  [frontend.md](../../review/references/frontend.md),
  [backend.md](../../review/references/backend.md),
  the implementation-feasibility lens in [`agents/codex/plan-validator.md`](../../../agents/codex/plan-validator.md), and
  [review-testplan.md](../../testing/references/review-testplan.md).
  Naming the menu here is what makes those lanes dispatchable: a lens this span
  omits cannot be selected, however clearly step 2 chose it.
- Reuse a reviewer only to clarify that reviewer's own finding in the same pass.
- The main thread revises `PLAN.md`; PROJECT.md stores state/pointers and final gate outcomes. Subagents return gated findings only.
- Continue after material findings are resolved and the cold read says Go; otherwise stop on a `BLOCKED` or `USER_DECISION` gate per `rules/gates.md`.
- For STANDARD plans or runs that hit 3+ review iterations, follow `rules/context-management.md`: after each review round, persist gate outcomes to PROJECT.md (`## Plan Review Round N`), then checkpoint + context_reset before the next revision-plus-rereview cycle. After a cold-read `No-Go`, checkpoint + context_reset before launching the revision. This is a hard gate — the gate history is needed for resume and pattern detection across rounds.

## Steps

### 1. Read the Plan

Read PROJECT.md to find the active plan pointer, then read `PLAN.md` when present. If no `PLAN.md` exists, fall back to plan content embedded in PROJECT.md. Verify the plan contains at least one of:
- `Implementation Plan` or `Accepted Solution` section
- `Test Strategy` section
- `Feature Brief` section

If no plan content found, stop: `"No plan found in PROJECT.md. Write a plan first, then run review-plan."`

### 2. Assess Plan Scope and Select Reviewers

Assess the plan's complexity to determine reviewer depth. Use the substance of the plan, not role labels, to choose reasoning effort per `rules/orchestration.md`.

| Plan scope | Reviewers | Cold read |
|------------|-----------|-----------|
| **Moderate** — single subsystem, well-understood pattern, no architectural decisions | 1 reviewer: the implementation-feasibility lens in [`agents/codex/plan-validator.md`](../../../agents/codex/plan-validator.md) | [`planning/references/finalize.md`](../../planning/references/finalize.md) |
| **Standard** — multi-system, real trade-offs, novel design, or ambiguous constraints | 3+ reviewers: `review/references/architecture.md` + the implementation-feasibility lens in `agents/codex/plan-validator.md` + [`testing/references/review-testplan.md`](../../testing/references/review-testplan.md) | `planning/references/finalize.md` |

**Conditional reviewers** (add to Standard plans when applicable):
- `review/references/frontend.md` — if plan touches frontend (React, CSS, UI components)
- `review/references/backend.md` — if plan touches backend (API, database, migrations)

State the scope assessment, which reviewers are selected, and why before launching.

### 3. Review Iterations

<!-- aitk-model-route:workflows.review-plan-selected -->
Launch the selected fresh reviewer subagents in parallel — one dispatch per lens,
each naming its own: [architecture.md](../../review/references/architecture.md),
the implementation-feasibility lens in [`agents/codex/plan-validator.md`](../../../agents/codex/plan-validator.md),
[frontend.md](../../review/references/frontend.md),
[backend.md](../../review/references/backend.md), or
[review-testplan.md](../../testing/references/review-testplan.md).
Use `review` for bounded implementation/test lanes; architecture and
security-sensitive lanes resolve to `deep-review`, which the manifest enforces as
a route floor rather than leaving to the dispatcher's reading of this sentence.
Each reviewer:
- Reads only PROJECT.md plus the active plan content needed for its lens
- Receives the exact inventoried reviewer contract closure inline from the route runner
- Produces a `rules/gates.md` gate block (`State`/`Reason`, plus strengths,
  issues, suggestions) — this is a **plan** fan-out, so lenses shared with
  code review use their plan-mode output. Each reviewer's own `State` is
  `PASS` or `RETRY` only — a fresh reviewer pass has no memory of prior
  rounds, so it cannot itself compute a repeat count or return `ESCALATE`.

After collecting gate blocks, track a `plan-review` round count (one counter
for the round, not per-lens) and apply `aitk.gates.decide_failure`:
- If every reviewer's `State` is `PASS` → proceed to step 4
- If any reviewer is `RETRY` and this is the first unresolved round →
  `decide_failure` returns `RETRY`: revise `PLAN.md` based on their feedback,
  or PROJECT.md only when the plan is embedded there, then re-run fresh
  reviewers for material revisions. Reuse the same reviewer only to clarify
  their own finding in the same pass.
- If any reviewer is still not `PASS` on a second consecutive round →
  `decide_failure` returns `ESCALATE`: escalate one cost dimension per
  `rules/gates.md`'s autonomous ladder (`rules/model-assignment.md`), then
  make one more revise-and-rereview attempt at the new tier
- If that attempt still leaves a reviewer not `PASS` and the ladder is
  exhausted → `BLOCKED` (unresolved, no ambiguity to ask about) or
  `USER_DECISION` (a real trade-off or scope question) — stop and surface it
  to the user
- Auto-iterate — do not ask the user whether to continue or which reviewers to re-run

### 4. Cold Read

Run `planning/references/finalize.md` on `deep-review` as a fresh-eyes final check. Translate its `Go`/`No-Go` recommendation into a `rules/gates.md` gate block the same way `finalize.md`'s Output section describes, tracking this checkpoint's own repeat count separately from step 3's:
- `Go` → `PASS`: proceed to step 5
- First `No-Go` → `RETRY`: revise the plan and re-run finalize-plan
- A second consecutive `No-Go` → `ESCALATE`: escalate one cost dimension per `rules/gates.md`'s autonomous ladder and make one more attempt
- If the ladder is exhausted and issues remain unresolved → `BLOCKED` (or `USER_DECISION` if it is a real trade-off) — stop and surface the blocking issues to the user

### 5. Update PROJECT.md

Write final gate outcomes to PROJECT.md:

```markdown
## Plan Review Gates
| Reviewer | Gate |
|----------|------|
| Architecture | PASS / RETRY / ESCALATE |
| Implementation | PASS / RETRY / ESCALATE |
| Test Plan | PASS / RETRY / ESCALATE |
| [conditional reviewers] | PASS / RETRY / ESCALATE |
| Cold Read | PASS / RETRY / ESCALATE |
```

### 6. Summary

```markdown
## Review-Plan Complete
[1-2 lines: plan quality assessment and whether it's ready for implementation]

### Review Gates
| Reviewer | Gate |
|----------|------|
| [reviewer] | [PASS / RETRY / ESCALATE] |

### Key Revisions
- [What changed based on review feedback — omit if no revisions needed]

### What to do next
- [Implement via create-feature or start implementation directly]
```

## Non-Negotiable Gates

- [ ] All applicable reviewers gated `PASS`
- [ ] Cold read gated `PASS` (Go)
- [ ] PROJECT.md updated with final gate outcomes
- [ ] Summary emitted

## PROJECT.md Update Discipline

- After each review round: append a `## Plan Review Round N` block with reviewer gate outcomes, key findings, and cold-read result (when run).
- After review iterations complete: write final gate outcomes under `## Plan Review Gates`.
- If revisions were made: update `PLAN.md`, or PROJECT.md only when the plan is embedded there.
- Per-round writes are hard gates before checkpoint + context_reset on STANDARD or 3+ round runs.

## Notes
- Standalone command — `create-feature` step 4 does the same work inline, but this is for one-off use
- Does not create or implement the plan — only reviews an existing one
- The runner derives and inlines the boundary's exact contract closure; callers
  cannot substitute arbitrary files, and routed workers do not load ambient skills.
