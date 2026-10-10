---
name: plan-review
description: "Use for the focused lenses a plan validator or deep code review applies: architecture, implementation feasibility, backend, frontend. Do NOT use for product scoping, running the validation loop, or implementation."
---

# Plan Review Lenses

Focused checklists, not a reviewer roster. The independent plan validator
(`agents/specialists/plan-validator.md`, run by
`planning/references/validate-plan.md`) covers architecture, feasibility, and
test strategy in one pass and inlines the feasibility checklist; the
independent code reviewer inlines the backend and frontend checklists; the
architecture lens runs as a conditional deep lens in code review.

| Lens | Reference | Used by |
|---|---|---|
| Architecture | [references/architecture.md](references/architecture.md) | `deep-review` code lens on architecture changes |
| Implementation feasibility | [references/implementation.md](references/implementation.md) | Plan validator, `phase-plan` and `fix-plan` modes |
| Backend | [references/backend.md](references/backend.md) | Independent code reviewer, for backend files in the diff |
| Frontend | [references/frontend.md](references/frontend.md) | Independent code reviewer, for frontend files in the diff |

Test-strategy review lives in `testing/references/review-testplan.md`.

## Output

Plan-domain findings are `[High]`, `[Medium]`, `[Low]` with a verdict, never a
numeric score. In code-lens mode the architecture lens reports `[major]`,
`[minor]`, `[nitpick]` per `rules/code-review.md`.
