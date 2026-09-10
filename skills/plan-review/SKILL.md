---
name: plan-review
description: "Use for the focused lenses a plan validator or deep code review applies: architecture, implementation feasibility, backend, frontend. Do NOT use for product scoping, running the validation loop, or implementation."
---

# Plan Review Lenses

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

Focused checklists, not a reviewer roster. The independent plan validator
(`agents/specialists/plan-validator.md`, run by
`planning/references/validate-plan.md`) covers architecture, feasibility, and
test strategy in one pass; these files hold the detailed checklists it and the
parent draw on. The architecture lens is also a conditional deep lens in code
review.

| Lens | Reference | Used by |
|---|---|---|
| Architecture | [references/architecture.md](references/architecture.md) | Plan validator focus; `deep-review` code lens on architecture changes |
| Implementation feasibility | [references/implementation.md](references/implementation.md) | Plan validator focus |
| Backend | [references/backend.md](references/backend.md) | Plan validator focus when the plan touches API, DB, or migrations |
| Frontend | [references/frontend.md](references/frontend.md) | Plan validator focus when the plan touches UI |

Test-strategy review lives in `testing/references/review-testplan.md`.

## Output

Plan-domain findings are `[High]`, `[Medium]`, `[Low]` with a verdict, never a
numeric score. In code-lens mode the architecture lens reports `[major]`,
`[minor]`, `[nitpick]` per `rules/code-review.md`.
