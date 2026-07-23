---
tier: Heavy
---

# Update Tests

Use this phase when the workflow needs to improve an existing test suite without running a larger end-to-end feature or bug workflow.

## Goal

Raise regression signal in the current suite with the smallest useful set of changes, while preserving local conventions and avoiding redundant test sprawl.

## Core Steps

1. Confirm the existing suite and the exact behaviors in scope.
2. Use sibling [review-tests.md](review-tests.md) findings and any QA use-case analysis to lock the must-update-now set.
3. Update existing tests first; add tests only where they fit the suite naturally.
4. Replace or remove low-signal tests only when the replacement is clearly stronger.
5. Write the failing test first when feasible. If blocked, record why before changing the suite.
6. Run targeted verification, then hand the changed files back for `review-code`.

## Output

```markdown
## Test Update Handoff

- Scope: <area, path, or function>
- Existing suite: <paths or files>
- Tests added or updated:
  - <file>
- Low-signal tests replaced or removed:
  - <file or none>
- Checks run:
  - <command>
- Remaining gaps:
  - <gap or none>
```
