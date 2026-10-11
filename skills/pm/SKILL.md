---
name: pm
description: "Use for product scoping before technical planning when requirements truly need it: a feature brief with goals, non-goals, acceptance criteria and, when rollout sequencing matters, milestones. Do NOT use for implementation planning, coding, or shipped-code review."
---

# PM

Optional product scoping before technical planning. Most `create-feature`
inputs do not need it: a tight change with obvious acceptance criteria or a
complete ticket is already the brief.

## Phases

| Phase | When | Reference |
|---|---|---|
| Create feature brief | Loose request, multiple product surfaces, or unclear acceptance criteria | [references/create-feature-brief.md](references/create-feature-brief.md) |

## Flow

Brief, then its self-check, then hand to `planning/`. For COMPLEX work,
`review-plan --pm` gives the plan validator the brief. Product and UX
trade-offs the brief cannot settle are `USER_DECISION`, surfaced once with
options.
