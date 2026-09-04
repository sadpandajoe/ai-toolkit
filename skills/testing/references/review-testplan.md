---
name: review-testplan
description: Review a plan's testing strategy for coverage approach, test layers, and edge cases.
tier: Heavy
---

# Test Plan Review

Evaluate whether the plan's testing strategy will provide meaningful regression protection.

Read before assessing: `rules/gates.md`, `rules/severity.md`

This lens sits in both a plan-review menu and a code-review menu, and the two want
different output. The route runner names which in its `lens_domain` header: `plan`
means the written plan, `code` means the diff. Read that field and use the matching
Output block below; the code-review grading contract arrives from the code fan-out
boundary itself, which is what knows its own domain. Neither vocabulary is a
default — guessing produced a lane that mixed plan-severity tags into a code
review that merges its own severity tags, where they are either dropped or
silently reweighted.

If PROJECT.md exists, read it first. If it does not exist, use the in-conversation context, plan, or diff as primary source.

## Focus Areas

Analyze:
- Coverage approach — identify what is tested and what is not
- Test layers — verify an appropriate mix of unit, integration, and e2e tests
- Edge cases — verify boundary conditions and error paths are covered
- Testable boundaries — verify the design supports clean test interfaces
- Mock strategy — verify mocking is appropriate and not excessive
- Test data strategy — verify test data is managed and reproducible
- CI/CD implications — verify tests will run reliably in CI

## Exclude

Do NOT comment on:
- Architecture decisions
- Code style or formatting
- UI design
- Implementation sequencing

## Output

When `lens_domain=plan` (reviewing the written plan):

```markdown
## Test Plan Review
### Strengths
- [What the plan does well for testing]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable testing improvement]
### Missing
- [What the plan should address from a testing perspective]
```

This body carries no verdict of its own — `agents/codex/plan-validator.md`'s
contract (inlined alongside this file at dispatch time) is what renders the
lens's `APPROVE`/`CHANGES REQUIRED`/`REPLAN` verdict, never a `rules/gates.md`
`## Gate` block or a numeric score. This lens has no memory of prior rounds,
so it cannot compute a repeat count or pick `ESCALATE`/`RETRY` itself: the
caller (`skills/workflows/references/review-plan.md`'s Review Iterations
step) translates the verdict into this workflow's own gate state and tracks
the repeat count across rounds.

When `lens_domain=code` (reviewing a diff): no score, and findings carry the
canonical severity tags from `rules/code-review.md` so they merge and dedupe
with the other code-review lanes.

```markdown
## Test Plan Review
### Findings
- [major] [Issue in the shipped testing change + why it matters]
- [minor] [Lower-consequence issue]
- [nitpick] [Optional polish]
### Strengths
- [What the change does well for testing]
### Suggestions
- [Specific, actionable testing improvement]
```
