# Create Tests

Use this phase when the workflow needs to create the first meaningful automated tests for an area that does not already have a real suite.

## Goal

Write the smallest set of high-signal tests that establishes real regression protection, follows project conventions, and gives later `update-tests` work something meaningful to improve.

Confirm first that there is no meaningful suite to improve. Let the sibling [review-tests.md](review-tests.md) decide which behaviors need coverage, and test each one at the narrowest layer that can prove it. A new test is done when it passes and you have watched it fail with the behavior broken (revert a line or flip the asserted value, then restore); a test that cannot be made to fail is noise, so rewrite it.

## Output

```markdown
## Handoff: tester
Status: completed | blocked
Scope: <behavior and files under test>
Layer: <unit | integration | component | e2e>
Tests: <files added or updated>
Evidence: <runner commands, pass/fail counts, the break-and-catch proof>
Product code touched: <none, or the seam and why>
Remaining gaps: <list, or none>
Next: <what the parent should run or review>
```
