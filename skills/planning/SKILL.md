---
name: planning
description: Producing a technical implementation plan, iterating it through reviewer feedback, finalizing with a cold read, or classifying review findings as plan-level (re-plan) vs code-level (fix in place). Do NOT use for product scoping (use pm/), writing code (use implement-change/), or reviewing finished code (use review/).
---

# Planning

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for technical planning phases — producing a plan, iterating it through review, finalizing it with a cold read, and routing review findings back if they indicate a plan-level issue.

## Distinction from sibling umbrellas

| Umbrella | Role |
|----------|------|
| `pm/` | Product scoping — brief, milestones, epic decomposition (precedes planning) |
| `planning/` (this skill) | Technical plan creation + iteration (follows PM) |
| `plan-review/` | Reviewer lenses that critique the technical plan (dispatched by this umbrella's iterate-review) |

PM → planning → implementation. This umbrella owns the middle phase.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Plan implementation | Produce the technical plan (approach, slices, test strategy) | [references/plan-implementation.md](references/plan-implementation.md) |
| Iterate plan review | Drive the parallel-reviewer loop until threshold met | [references/iterate-review.md](references/iterate-review.md) |
| Finalize plan | Cold-read gate — stay or move decision before implementation | [references/finalize.md](references/finalize.md) |
| Feedback classify | Route review findings: code-level (fix in loop) vs plan-level (re-plan) | [references/feedback-classify.md](references/feedback-classify.md) |

## Composition Flow

Standard substantial planning:
1. `plan-implementation` → draft plan
<!-- aitk-model-route:planning.loop-summary -->
2. [`iterate-review`](references/iterate-review.md) → dispatches `plan-review/` reviewers on `review`/`deep-review` until 8/10 threshold
3. `finalize` → cold-read "stay or move" gate
4. Hand off to implementation

During post-implementation review, if findings surface:
5. `feedback-classify` → route to plan-level re-plan OR continue code-level fix

## Invocation

- `plan-implementation` — orchestrator reads reference and produces draft (inline or subagent)
- `iterate-review` — orchestrator reference that drives the loop (references `plan-review/` subagents)
- `finalize` — reviewer subagent prompt (cold read, fresh context)
- `feedback-classify` — classifier (produces routing decision)

## Notes

<!-- aitk-model-route:planning.loop-ownership -->
- [`iterate-review`](references/iterate-review.md) is the loop-runner that dispatches `plan-review/` lens subagents on `review`/`deep-review`. They work together: this umbrella owns the loop; `plan-review/` owns the lenses.
- `finalize` fires once per plan iteration cycle as the last gate before implementation begins.
- `feedback-classify` is how the planning umbrella reaches back into implementation/review to say "this isn't a code fix — re-plan."
- End-to-end sequencing belongs in the selected canonical workflow reference.
  This skill owns planning phases only; the workflow routes implementation,
  review, QA, and reporting to their domain skills.
