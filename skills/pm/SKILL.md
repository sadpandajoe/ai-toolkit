---
name: pm
description: "Use for product scoping before technical planning when requirements truly need it: briefs, acceptance criteria, milestones, and epic decomposition. Do NOT use for implementation planning, coding, or shipped-code review."
---

# PM

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Optional product scoping before technical planning. Most `create-feature`
inputs do not need it: a tight change with obvious acceptance criteria or a
complete ticket is already the brief.

## Phases

| Phase | When | Reference |
|---|---|---|
| Create feature brief | Loose request, multiple product surfaces, or unclear acceptance criteria | [references/create-feature-brief.md](references/create-feature-brief.md) |
| Plan milestones | Rollout, compatibility, or dependency sequencing matters | [references/plan-milestones.md](references/plan-milestones.md) |
| Review feature brief | Checklist the parent applies to its own brief; for COMPLEX work the plan validator receives the brief (`review-plan --pm`) | [references/review-feature-brief.md](references/review-feature-brief.md) |
| Decompose epic | Multi-story epic needs a dependency-ordered wave plan | [references/decompose-epic.md](references/decompose-epic.md) |

## Flow

Ambiguous scope: brief → milestones if needed → self-review against the
checklist → hand to `planning/`. Epics: decompose first, then the single-story
flow per wave. Product and UX trade-offs the brief cannot settle are
`USER_DECISION`, surfaced once with options.
