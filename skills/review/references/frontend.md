---
name: review-frontend
description: Review plan from a frontend and UI/UX perspective.
tier: Heavy
---

# Frontend Review

Evaluate the plan's frontend approach including component design, state management, and user experience.

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
- Component design — verify components are reusable, composable, and appropriately sized
- State management — verify where state lives and confirm data flow is unambiguous
- UX flows — verify user interactions are well-defined and complete
- Accessibility — verify keyboard navigation, screen reader support, ARIA attributes, and contrast
- Performance — verify rendering efficiency, bundle size impact, and lazy loading usage
- Error and loading states — verify the user sees appropriate feedback when things go wrong or are loading
- Responsive design — verify the layout works across screen sizes
- Consistency with existing frontend patterns in the codebase

## Exclude

Do NOT comment on:
- Backend API internals
- Database design
- Deployment infrastructure
- Server-side implementation details

## Output

When `lens_domain=plan` (reviewing the written plan):

```markdown
## Frontend Review
### Score: X/10
### Strengths
- [What the plan does well for frontend]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable frontend improvement]
### Missing
- [What the plan should address from a frontend perspective]
```

When `lens_domain=code` (reviewing a diff): no score, and findings carry the
canonical severity tags from `rules/code-review.md` so they merge and dedupe
with the other code-review lanes.

```markdown
## Frontend Review
### Findings
- [major] [Issue in the shipped frontend change + why it matters]
- [minor] [Lower-consequence issue]
- [nitpick] [Optional polish]
### Strengths
- [What the change does well for frontend]
### Suggestions
- [Specific, actionable frontend improvement]
```
