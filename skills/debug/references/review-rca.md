---
name: review-rca
description: Review root cause analysis and proposed fix before implementation.
tier: Heavy
---

# Review RCA

Review the root cause analysis and proposed solution before implementation.
This is a shared validator, not a persona-owned workflow.

Use `rca` when the causal chain is bounded and evidence is direct. Use
`deep-rca` when causes compete, reproduction is intermittent, history matters,
or multiple systems participate. Both routes are read-only.

If PROJECT.md exists, read it first. If it does not exist, use the in-conversation context, plan, or diff as primary source.

Focus on these sections if present:
- Issue
- Evidence
- Root Cause
- Proposed Fix
- Tests

## Root Cause Validation

Determine whether the stated root cause is plausible.

Check:
- whether the explanation matches the behavior of the code
- whether alternative root causes could exist
- whether the evidence is sufficient
- whether assumptions require validation

Identify missing investigation steps if the RCA is uncertain.

## Proposed Fix Evaluation

Analyze the proposed solution.

Determine:
- whether the fix actually addresses the root cause
- whether the approach introduces unnecessary complexity
- whether the plan could introduce new bugs
- whether important edge cases are unhandled

## Risk Analysis

Identify possible failure scenarios such as:
- race conditions
- state inconsistencies
- partial failures
- integration issues
- performance risks

## Output

```markdown
## RCA Review
### Score: X/10
### Strengths
- [What the RCA does well — thorough evidence, clear causal chain, etc.]
### Issues
- [High/Medium/Low] [Issue — why it matters for the fix]
### Suggestions
- [Specific improvement to the analysis or proposed fix]
### Missing
- [What the RCA should address — alternative causes, untested assumptions, etc.]
```
