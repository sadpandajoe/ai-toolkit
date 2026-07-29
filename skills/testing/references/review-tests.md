---
name: review-tests
description: Evaluate test quality, regression signal, production failure scenarios, and recommended safeguards before merge.
tier: Heavy
---

# Review Tests

## Required Context

Read before starting: `rules/code-review.md`, `rules/severity.md`,
`rules/stop-rules.md`.
Findings use the canonical `[major]` / `[minor]` / `[nitpick]` tags.

## Goal

Evaluate the tests related to the current change.

If PROJECT.md exists, read it first to understand the issue, root cause, and expected behavior. If it does not exist, use the in-conversation context, plan, or diff as primary source.

Focus on whether the test suite provides meaningful regression protection and whether the change could fail in production even if tests pass.

## Behavioral Coverage

Identify the real behaviors the tests validate.

Determine:
- whether tests validate actual system behavior
- whether important state transitions are exercised
- whether critical failure scenarios are tested

## Weak or Low-Signal Tests

Identify weak tests such as:
- tests heavily dependent on implementation details
- overly mocked tests that bypass real logic
- brittle tests that fail for irrelevant reasons
- redundant tests that add little value
- tests validating setup rather than behavior

For each weak or low-signal test:
- explain why it provides low regression signal
- determine whether it should be improved, merged, moved to a lower layer, or removed
- suggest how to rewrite it into a higher-signal test if possible

## Missing Behavioral Coverage

Identify behaviors that are not tested, such as:
- edge cases
- concurrent operations
- failure paths
- state inconsistencies
- integration points

## Production Failure Scenarios

Assume the current change has been deployed to production.

Identify realistic scenarios where the system could fail even if the current tests pass:
- race conditions
- unexpected input
- state inconsistencies
- partial failures
- integration failures
- performance or timing issues

Determine whether existing tests would detect these failures. Identify gaps in regression protection.

## Suite Simplification Opportunities

Identify tests that should be:
- removed because they provide little value
- merged because they overlap heavily
- moved to unit/integration level instead of higher-level tests
- replaced with a smaller number of higher-signal tests

## Output

```markdown
## Test Review
### Score: X/10
### Strengths
- [Behavioral coverage, high-signal tests, suite efficiency]
### Issues
- [High/Medium/Low] [Weak tests, missing coverage, production blind spots — why each matters]
### Suggestions
- [Tests to add, simplification opportunities, defensive checks, monitoring]
### Missing
- [Untested behaviors, production failure scenarios not covered, safeguards needed]
```
