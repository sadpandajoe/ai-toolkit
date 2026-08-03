---
name: review-testplan
description: Review a plan's testing strategy for coverage approach, test layers, and edge cases.
tier: Heavy
---

# Test Plan Review

Evaluate whether the plan's testing strategy will provide meaningful regression protection.

Read before scoring: `rules/scoring.md`, `rules/severity.md`

This lens sits in both a plan-review menu and a code-review menu, and the two want
different output. The route runner names which in its `lens_domain` header: `plan`
means the written plan, `code` means the diff. Read that field and use the matching
Output block below; the code-review grading contract arrives from the code fan-out
boundary itself, which is what knows its own domain. Neither vocabulary is a
default — guessing produced a lane that returned `X/10` scores into a code review
that merges severity tags, where they are either dropped or silently reweighted.

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
### Score: X/10
### Strengths
- [What the plan does well for testing]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable testing improvement]
### Missing
- [What the plan should address from a testing perspective]
```

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
