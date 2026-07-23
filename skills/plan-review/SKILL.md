---
name: plan-review
description: "Use for reviewer lenses that critique a technical plan before implementation. Do NOT use for product scoping, finished-code review, or implementation."
---

# Plan Review

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for reviewer lenses that critique a *technical plan* before implementation starts. Each reference is a reviewer subagent prompt applying a specific angle to the plan.

## Distinction from other review umbrellas

| Umbrella | Reviews | When |
|----------|---------|------|
| `plan-review/` (this skill) | Technical plan | During `planning/references/iterate-review.md` loop (pre-implementation) |
| `pm/review-feature-brief` | Feature brief (scope/AC/milestones) | During PM iteration (pre-planning) |
| `review/` | Shipped code | `review-code`, `review-pr` (post-implementation) |
| `testing/review-tests` and `review-testplan` | Test code and test strategy | During review (code) or plan-review (strategy) |

## Reviewer Lenses

| Lens | Always-on | When conditional | Reference |
|------|-----------|------------------|-----------|
| Architecture | Substantial plans | — | [references/architecture.md](references/architecture.md) |
| Implementation feasibility | Substantial plans | — | [references/implementation.md](references/implementation.md) |
| Backend | — | Plan touches API / DB / migrations | [references/backend.md](references/backend.md) |
| Frontend | — | Plan touches React / CSS / UI components | [references/frontend.md](references/frontend.md) |

(Test-strategy plan review is in `testing/references/review-testplan.md` — it always fires for substantial plans alongside this umbrella's always-ons.)

## Invocation

Each reference is an independent-review prompt. The `planning` skill's
iterate-review reference dispatches them with `fresh_subagent` and
`parallel_fanout`; provider bindings choose concrete syntax.

Map the tier to the current runtime's actual model or reasoning-effort controls at dispatch time.

Each returns severity-tagged findings + score. The iterate loop continues until the 8/10 threshold is met or a blocker surfaces.

## Notes

- "Plan-review" is a distinct persona from "code-review". A plan reviewer reasons about whether the plan is *achievable* and *well-scoped*; a code reviewer reasons about whether the code is *correct* and *safe*.
- Same conceptual reviewer personas exist for code (`review/references/code-quality.md`, `review/references/adversarial.md`, `testing/references/review-tests.md`) — different lens, different phase.
