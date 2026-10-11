---
name: planning
description: Use for technical planning sized to the work: a compact inline plan for STANDARD changes, a just-in-time phase plan, an architecture decomposition for MULTI_PHASE work, or independent plan validation. Do NOT use for product scoping (pm/), writing code (implement-change/), or reviewing finished code (review/).
---

# Planning

Complexity decides the reasoning tier; size and shape decide the planning
shape. Plan only as much as the next verifiable unit needs.

| Situation | Who plans | Reference |
|---|---|---|
| STANDARD, SINGLE_PHASE | Parent, inline | [references/plan-implementation.md](references/plan-implementation.md) |
| COMPLEX, SINGLE_PHASE | Planner (`agents/specialists/planner.md`, `planning` route) in `phase-plan` mode; the parent writes its section verbatim | [references/plan-implementation.md](references/plan-implementation.md) |
| MULTI_PHASE, any complexity | Decompose first, then one phase at a time | [references/decompose-work.md](references/decompose-work.md), then [references/plan-implementation.md](references/plan-implementation.md) per phase |
| BATCHED | Parent, inline: one transformation, waves, repeated verification | [references/plan-implementation.md](references/plan-implementation.md) |
| Any decomposition, any COMPLEX plan, or a STANDARD plan at `LOW` classification confidence | Independent validator | [references/validate-plan.md](references/validate-plan.md) |

Each plan is a reasoning unit with the retry budget in `rules/gates.md`.

## Phase-Size Guard

Split a phase once more before implementation when any of these hold:

- its plan names more than 10 files, or its projected diff exceeds 500 changed
  lines (generated files and lockfiles excluded);
- it is a horizontal layer (all models, then all APIs, then all UI) rather
  than a vertical slice;
- it would leave the system broken if deployed alone;
- a reviewer could not read it in one sitting.

Never let a later phase plan silently rewrite accepted global architecture; a
changed invariant is `RECLASSIFY` and an explicit update to the decomposition
artifact.

## Ownership

The parent writes `PLAN.md` and the routing snapshot (`bin/aitk project-state
phases`). Planners and validators return text: the planner returns the `PLAN.md`
section (and, for a decomposition, its `phases-json` block), which the parent
writes and records verbatim. End-to-end sequencing belongs to
the goal workflow reference, not here.
