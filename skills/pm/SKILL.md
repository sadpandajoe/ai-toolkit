---
name: pm
description: "Use for product scoping before technical planning: briefs, acceptance criteria, milestones, and epic decomposition. Do NOT use for implementation planning, coding, or shipped-code review."
---

# PM

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Umbrella for product-management planning phases — producing and reviewing scope-level artifacts before technical planning begins.

## Distinction vs planning/

- **pm/** (this skill) — product scoping: what problem, who for, acceptance criteria, milestones, epic decomposition
- **planning/** — technical planning: how to build it, implementation slices, test strategy
- **plan-review/** — reviewer lenses that critique technical plans

PM is strategic; planning is engineering. PM output feeds the planning phase.

## Phases

| Phase | When | Reference |
|-------|------|-----------|
| Create feature brief | Non-trivial scope — needs explicit problem statement + AC | [references/create-feature-brief.md](references/create-feature-brief.md) |
| Plan milestones | Scope has natural phases, rollout concerns, or dependencies to sequence | [references/plan-milestones.md](references/plan-milestones.md) |
| Review feature brief | Brief exists, needs critique for scope clarity + AC quality | [references/review-feature-brief.md](references/review-feature-brief.md) |
| Decompose epic | Input is a multi-story epic — produce wave plan (dependency-ordered) | [references/decompose-epic.md](references/decompose-epic.md) |

## When to Skip PM

Not every `create-feature` input needs a PM layer. Skip when:
- The work is a single tightly-scoped change with obvious AC
- User provided a complete ticket with clear scope/AC/milestones already
- Trivial/moderate complexity gate classification

Use PM when:
- Scope is ambiguous or could creep
- Milestones matter (rollout, compatibility, dependencies)
- User provided a loose request that needs concrete scoping
- Input is a multi-story epic → `decompose-epic` first

## Composition Flow

Full PM sequence for ambiguous scope:
1. `create-feature-brief` → brief with problem/users/AC/constraints
2. `plan-milestones` → milestones if needed
3. `review-feature-brief` → critique + iterate
4. Hand off to `planning/` umbrella for technical plan

For multi-story epics:
1. `decompose-epic` → wave plan
2. Per wave, per story: run the full single-story flow

## Notes

- `decompose-epic` is placed here (PM) rather than in planning because epic → wave mapping is fundamentally about scope sequencing (a PM concern), not about how to build any individual story.
- `review-feature-brief` is a reviewer subagent prompt (same shape as reviewers in review/ and plan-review/).
