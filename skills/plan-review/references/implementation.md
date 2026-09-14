---
name: review-implementation
description: Review plan from an implementation feasibility and sequencing perspective.
tier: Heavy
---

# Implementation Review

Evaluate whether the plan is practically implementable with realistic effort and sequencing.

Read before grading: `rules/severity.md`

If PROJECT.md exists, read it first. If it does not exist, use the in-conversation context, plan, or diff as primary source.

## Focus Areas

Analyze:
- Step sequencing — are dependencies between steps respected?
- Effort realism — are estimates reasonable for each step?
- Dependency availability — do required libraries/APIs exist?
- Consistency with existing codebase patterns and conventions
- Incremental delivery — is each phase a small, independently deployable PR that can be shipped without leaving the system in a broken state?
- Standalone migration PRs — migrations must be bundled with the code that uses them (if the migration ships alone and needs revert, dependent code may already be deployed in another PR)
- Vertical slices — prefer end-to-end feature slices over horizontal layers (all models → all APIs → all UI) (each slice is deployable and testable independently; horizontal layers leave the system partially functional between PRs)
- Migration concerns — backward compatibility, data migration, rollback
- Risk of each step — what could go wrong?

## Exclude

Do NOT comment on:
- High-level architecture decisions
- Test strategy details
- UI design choices
- Code style

## Output

```markdown
## Implementation Review
### Strengths
- [What the plan does well for implementability]
### Issues
- [High/Medium/Low] [Issue + why it matters]
### Suggestions
- [Specific, actionable implementation improvement]
### Missing
- [What the plan should address from an implementation perspective]
```
