---
name: planning
description: Producing a technical implementation plan, iterating it through reviewer feedback, finalizing with a cold read, or classifying review findings as plan-level (re-plan) vs code-level (fix in place). Do NOT use for writing code (use implement-change/) or reviewing finished code (use review/).
---

# Planning

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for technical planning phases — producing a plan, iterating it through review, finalizing it with a cold read, and routing review findings back if they indicate a plan-level issue.

## Distinction from sibling umbrellas

| Umbrella | Role |
|----------|------|
| `planning/` (this skill) | Technical plan creation + iteration |
| `review/` (plan lenses) + `agents/codex/plan-validator.md` | Reviewer lenses that critique the technical plan (dispatched by `workflows/references/review-plan.md` for `SINGLE_PHASE`/`BATCHED`, or by `plan-phase.md`'s six-state gate for `MULTI_PHASE`) |

This umbrella owns the planning phase, ahead of implementation.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Plan implementation | Produce the technical plan (approach, slices, test strategy) | [references/plan-implementation.md](references/plan-implementation.md) |
| Finalize plan | Cold-read gate — stay or move decision before implementation | [references/finalize.md](references/finalize.md) |
| Feedback classify | Route review findings: code-level (fix in loop) vs plan-level (re-plan) | [references/feedback-classify.md](references/feedback-classify.md) |

Shape note: [`decompose-work`](references/decompose-work.md) and
[`plan-phase`](references/plan-phase.md) are the live `MULTI_PHASE` path —
the former decomposes the whole unit once, the latter plans one phase at a
time against that decomposition, each gated through `rules/gates.md`'s
six-state contract instead of a numeric threshold. `create-feature`'s
Multi-Phase Path already routes every `MULTI_PHASE` unit through both today.
For `SINGLE_PHASE`/`BATCHED`, the 8/10-threshold reviewer-iterate-then-cold-read
loop is owned directly by `skills/workflows/references/review-plan.md`
(steps 2–4), not by this umbrella — `iterate-review.md` (the umbrella-owned
version of that loop) was deleted in Wave D once its only caller migrated.

## Composition Flow

Route by `execution_shape` (`aitk/size_axis.py`), set by the caller's own
size classification before this umbrella is entered:

**`MULTI_PHASE`** — the live path (e.g. `create-feature`'s Multi-Phase Path):
1. [`decompose-work`](references/decompose-work.md) → architecture
   decomposition, once for the whole unit, gated `PASS` via the six-state
   contract before any phase is planned
2. Per phase, in dependency order: [`plan-phase`](references/plan-phase.md)
   → this phase's plan, gated `PASS` via the six-state contract
3. Hand off each phase to implementation as it gates `PASS`

**`SINGLE_PHASE` / `BATCHED`**:
1. [`plan-implementation`](references/plan-implementation.md) → draft plan
2. `skills/workflows/references/review-plan.md` steps 2–4 (called directly by
   the goal workflow, not by this umbrella) → dispatches the plan-domain
   reviewers (`review/references/{architecture,frontend,backend}.md` plus
   `agents/codex/plan-validator.md`'s implementation-feasibility lens) on
   `review`/`deep-review` until 8/10 threshold, then
   [`finalize`](references/finalize.md) cold-read "stay or move" gate
3. Hand off to implementation

During post-implementation review, if findings surface:
4. `feedback-classify` → route to plan-level re-plan OR continue code-level fix

## Invocation

- `plan-implementation` — orchestrator reads reference and produces draft (inline or subagent)
- `finalize` — reviewer subagent prompt (cold read, fresh context)
- `feedback-classify` — classifier (produces routing decision)

## Notes

- For `SINGLE_PHASE`/`BATCHED`, the goal workflow (not this umbrella) drives
  the reviewer-iterate-then-cold-read loop directly via
  `skills/workflows/references/review-plan.md` steps 2–4, dispatching the
  plan-domain lens subagents on `review`/`deep-review`. `iterate-review.md`
  was this umbrella's own copy of that loop; it was deleted in Wave D once
  `review-plan` (its only remaining caller) migrated to dispatching the
  lenses directly instead of going through it.
- `finalize` fires once per plan iteration cycle as the last gate before implementation begins.
- `feedback-classify` is how the planning umbrella reaches back into implementation/review to say "this isn't a code fix — re-plan."
- End-to-end sequencing belongs in the selected canonical workflow reference.
  This skill owns planning phases only; the workflow routes implementation,
  review, QA, and reporting to their domain skills.
