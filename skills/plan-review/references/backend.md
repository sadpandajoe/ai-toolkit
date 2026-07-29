---
name: review-backend
description: Review plan from a backend, API, and data modeling perspective.
tier: Heavy
---

# Backend Review

Evaluate the plan's backend approach including API design, data modeling, and security.

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
- API design — verify RESTful conventions, consistent naming, and versioning
- Data modeling — verify schema design, relationships, constraints, and indexes
- Security — verify authentication, authorization, input validation, and injection prevention
- Performance — verify query efficiency, absence of N+1 problems, and caching strategy
- Error handling — verify consistent error responses, meaningful messages, and retry logic
- Migrations — verify safe schema changes, backward compatibility, and rollback plan
- External integrations — verify third-party API usage, message queues, and caching layers
- Consistency with existing backend patterns in the codebase

## Exclude

Do NOT comment on:
- UI components or frontend state
- CSS or styling
- Frontend build tooling
- Client-side routing

## Output

When `lens_domain=plan` (reviewing the written plan):

```markdown
## Backend Review
### Score: X/10
### Strengths
- [What the plan does well for backend]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable backend improvement]
### Missing
- [What the plan should address from a backend perspective]
```

When `lens_domain=code` (reviewing a diff): no score, and findings carry the
canonical severity tags from `rules/code-review.md` so they merge and dedupe
with the other code-review lanes.

```markdown
## Backend Review
### Findings
- [major] [Issue in the shipped backend change + why it matters]
- [minor] [Lower-consequence issue]
- [nitpick] [Optional polish]
### Strengths
- [What the change does well for backend]
### Suggestions
- [Specific, actionable backend improvement]
```
