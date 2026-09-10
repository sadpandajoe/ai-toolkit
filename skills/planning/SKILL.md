---
name: planning
description: Use for technical planning sized to the work: a compact inline plan for STANDARD changes, a just-in-time phase plan, an architecture decomposition for MULTI_PHASE work, independent plan validation, or classifying review findings as plan-level. Do NOT use for product scoping (pm/), writing code (implement-change/), or reviewing finished code (review/).
---

# Planning

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Complexity decides the reasoning tier; size and shape decide the planning
shape. Plan only as much as the next verifiable unit needs.

| Situation | Who plans | Reference |
|---|---|---|
| STANDARD, SINGLE_PHASE | Parent, inline | [references/plan-implementation.md](references/plan-implementation.md) |
| COMPLEX, SINGLE_PHASE | `planning` route (Fable) in `phase-plan` mode | [references/plan-phase.md](references/plan-phase.md) |
| MULTI_PHASE, any complexity | Decompose first, then one phase at a time | [references/decompose-work.md](references/decompose-work.md), then [references/plan-phase.md](references/plan-phase.md) |
| BATCHED | Parent, inline: one transformation, waves, repeated verification | [references/plan-implementation.md](references/plan-implementation.md) |
| Any decomposition, any COMPLEX plan, or a STANDARD plan at `LOW` classification confidence | Independent validator | [references/validate-plan.md](references/validate-plan.md) |
| Review finding looks plan-level | Parent | [references/feedback-classify.md](references/feedback-classify.md) |

## Bounded Reasoning

Each reasoning unit (a decomposition, a phase plan, a fix plan) gets one
attempt and one informed retry under `rules/gates.md`. Editorial fixes do not
consume the budget; reasoning failures do. After two, escalate only the
unresolved decision with a compact adjudication package: one dimension at a
time, more effort, then a different model, `xhigh` last.

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
phases`). Planners and validators return text. End-to-end sequencing belongs to
the goal workflow reference, not here.
