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
security-sensitive lanes resolve to `deep-review`. This split is caller
policy this step enforces, not something the manifest or resolver knows
about — the per-lens fan-out mechanism that would have carried a lens into
routing was retired, so `workflows.review-plan-selected` accepts either
route for any lens; nothing stops a miscoded dispatch step from sending the
architecture lens through `review` instead, which is why this sentence, not
a build-time check, is the actual floor.
Each reviewer:
- Reads only PROJECT.md plus the active plan content needed for its lens
- Receives the exact inventoried reviewer contract closure inline from the route runner
- Returns its verdict and findings as the Evidence summary field of the
  `rules/specialist-handoff.md` output contract, per the native worker
  contracts (`agents/claude/plan-review-worker.md` /
  `deep-plan-review-worker.md`) or the Codex contract
  (`agents/codex/plan-validator.md`) — `APPROVE`, `CHANGES REQUIRED`, or
  `REPLAN`, never a `rules/gates.md` block directly and never a numeric
  score. A fresh reviewer pass has no memory of prior rounds, so it cannot
  itself compute a repeat count or pick `ESCALATE`/`RETRY`; this step owns
  translating each verdict into this workflow's own gate state.

### Worker verdict → gate mapping

This workflow — not the worker — owns the translation below, since the
worker contract only renders a verdict (`agents/codex/plan-validator.md`:
"this contract renders the verdict, the calling workflow owns the gate
mapping"):

| Verdict | Gate state | Why |
|---|---|---|
| `APPROVE` | `PASS` | Lens found nothing blocking. |
| `CHANGES REQUIRED` | `RETRY` (`kind: reasoning`) | Concrete, fixable issues in the artifact as written — revise `PLAN.md` and re-run the same lens. |
| `REPLAN` | `RETRY` (`kind: reasoning`) on the first unresolved round, `USER_DECISION` immediately (uncounted) if the invalidated assumption is itself a trade-off/scope call | The artifact's premise is wrong, not just its details — a disproven assumption, an infeasible slice baked into the shape of the plan. A wrong premise warrants reassessment, not an automatic declaration that the escalation ladder is exhausted (`rules/gates.md`'s `BLOCKED` definition reserves that state for exactly that exhaustion). `USER_DECISION` is the one exit that skips the ladder entirely, and only for a genuine user-owned trade-off — not a default alternative to `BLOCKED`. |

`REPLAN`'s `RETRY` differs from `CHANGES REQUIRED`'s in what the revision
attempt does: `CHANGES REQUIRED` patches `PLAN.md` in place and re-runs the
same lens. `REPLAN`'s fix attempt reworks the invalidated premise or
assumption itself — re-examine the plan's scope/approach in light of what the
reviewer disproved (this may itself change the Moderate/Standard scope call
from step 2) before revising `PLAN.md`. Because a premise change is material
to every lens's assessment, not just the one that caught it, re-run fresh
reviewer subagents for the full selected lens menu per the Command Contract's
"fresh reviewer subagents for each review pass after material plan
revisions" — not only the lens that returned `REPLAN`. Patching surface
details without addressing the invalidated premise is not a valid `RETRY`
attempt for a `REPLAN`.

After translating every reviewer's verdict, track a `plan-review` round count
(one counter for the round, not per-lens) and apply
`aitk.gates.decide_failure` to the translated states. `REPLAN` and
`CHANGES REQUIRED` share this same counter — both are `reasoning`-kind
failures of the same checkpoint, so two consecutive rounds of either (in any
combination) escalate together, not as separate ladders:
- If any reviewer's `REPLAN` translates to `USER_DECISION` (a real
  trade-off/scope call — workers never return `USER_DECISION` as a verdict
  themselves, only this workflow's translation reaches that state) → stop
  this round and surface it to the user regardless of the other reviewers'
  verdicts. This is not a failure and does not advance the round count.
- If every reviewer's translated state is `PASS` → proceed to step 4
- If any reviewer is `RETRY` (from `CHANGES REQUIRED` or a first-unresolved-
  round `REPLAN`) → `decide_failure` returns `RETRY`: for `CHANGES REQUIRED`,
  revise `PLAN.md` based on their feedback and re-run the same lens; for
  `REPLAN`, rework the invalidated premise per the note above, then revise
  `PLAN.md` (or PROJECT.md only when the plan is embedded there) and re-run
  fresh reviewers for the full selected lens menu, since a premise change is
  material to every lens, not just the one that caught it. Reuse the same
  reviewer only to clarify their own finding in the same pass.
- If any reviewer is still not `PASS` on a second consecutive round →
  `decide_failure` returns `ESCALATE`: escalate one cost dimension per
  `rules/gates.md`'s autonomous ladder (`rules/model-assignment.md`), then
  make one more revise-and-rereview attempt at the new tier — the same
  premise-rework attempt described above if the still-unresolved reviewer's
  verdict is `REPLAN`
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
