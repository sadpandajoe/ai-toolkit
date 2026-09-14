---
tier: Heavy
---

# Validate Feature

Use this phase after a feature slice or full feature has passed code-level verification and review.

## Goal

Confirm the implemented behavior satisfies the feature acceptance criteria in the user-visible workflow, and identify any remaining validation gaps before PR or release handoff.

For UI and workflow features, use Playwright MCP as the default validation path when the app is runnable. If browser automation or the app environment is unavailable, record the blocker explicitly instead of implying full validation.

## Inputs

- Feature brief or acceptance criteria.
- Implemented slice or feature summary.
- Review gate status.
- App URL or environment state, when user-visible behavior changed.

## Core Steps

1. Map each relevant acceptance criterion to one validation action.
2. Exercise the primary happy path in the runnable environment.
3. Exercise the most important edge or permission/data-state path.
4. Capture evidence for material passes or failures.
5. Mark each criterion `met`, `partial`, `failed`, or `blocked`.
6. Call out gaps caused by missing environment access, missing data, feature flags, or unavailable browser tooling.

## Output

```markdown
## Feature Validation

- Result: <pass / partial / fail / blocked>
- Validation path: <Playwright MCP / manual / mixed / blocked>
- Acceptance criteria:
  - <criterion>: <met / partial / failed / blocked> - <evidence>
- Evidence:
  - <screenshot/video/log path, or none>
- Remaining risks:
  - <risk or none>
- Blockers:
  - <env/setup/data gaps, if any>
```
