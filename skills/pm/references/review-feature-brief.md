---
name: review-feature-brief
description: Review a feature brief for scope clarity, acceptance quality, milestone framing, and product-level risks.
tier: Heavy
---

# Feature Brief Review

Review the product-facing feature brief before technical planning begins.

Read before grading: `rules/severity.md`

If PROJECT.md exists, read it first. If it does not exist, use the in-conversation context, plan, or diff as primary source.

## Focus Areas

Analyze:
- scope clarity and boundary definition
- goal versus non-goal separation
- acceptance criteria quality and testability
- milestone framing and sequencing
- unstated product assumptions
- rollout, dependency, or risk gaps

## Exclude

Do NOT comment on:
- code style or implementation details
- low-level architecture choices
- file organization or naming

## Output

```markdown
## Feature Brief Review
### Strengths
- [What the brief does well]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable improvement]
### Missing
- [What the brief still needs before technical planning]
```
