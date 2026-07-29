---
name: review-architecture
description: Review plan from a system design and architecture perspective.
tier: Heavy
---

# Architecture Review

Evaluate the plan's architectural decisions, component boundaries, and system design.

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
- System design and component boundaries
- Coupling between components — are dependencies clean?
- Scalability — will the design handle growth?
- Consistency with existing codebase patterns and conventions
- API contracts and interface design
- Data flow and state management approach
- Separation of concerns

## Exclude

Do NOT comment on:
- Code style or formatting
- Test implementation details
- UI/UX specifics
- Implementation sequencing

## Output

When `lens_domain=plan` (reviewing the written plan):

```markdown
## Architecture Review
### Score: X/10
### Strengths
- [What the plan does well architecturally]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable architectural improvement]
### Missing
- [What the plan should address from an architecture perspective]
```

When `lens_domain=code` (reviewing a diff): no score, and findings carry the
canonical severity tags from `rules/code-review.md` so they merge and dedupe
with the other code-review lanes.

```markdown
## Architecture Review
### Findings
- [major] [Issue in the shipped architecture change + why it matters]
- [minor] [Lower-consequence issue]
- [nitpick] [Optional polish]
### Strengths
- [What the change does well architecturally]
### Suggestions
- [Specific, actionable architectural improvement]
```
