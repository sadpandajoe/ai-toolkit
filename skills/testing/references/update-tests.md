# Update Tests

Use this phase when the workflow needs to improve an existing test suite without running a larger end-to-end feature or bug workflow.

## Goal

Raise regression signal in the current suite with the smallest useful set of changes, while preserving local conventions and avoiding redundant test sprawl.

Let the sibling [review-tests.md](review-tests.md) findings and any QA use-case analysis set the must-update-now list. Update existing tests before adding new ones, add tests only where they fit the suite naturally, and replace or remove a low-signal test only when the replacement is clearly stronger. Write the failing test first when feasible; when blocked, record why before changing the suite. Run the targeted tests, then hand the changed files back for `review-code`.

## Output

```markdown
## Handoff: tester
Status: completed | blocked
Scope: <behavior and files under test>
Layer: <unit | integration | component | e2e>
Tests: <files added or updated>
Replaced or removed: <low-signal tests, or none>
Evidence: <runner commands, pass/fail counts>
Product code touched: <none, or the seam and why>
Remaining gaps: <list, or none>
Next: <what the parent should run or review>
```
