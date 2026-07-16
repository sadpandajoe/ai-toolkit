---
tier: Heavy
---

# Create Tests

Use this phase when the workflow needs to create the first meaningful automated tests for an area that does not already have a real suite.

## Goal

Write the smallest set of high-signal tests that establishes real regression protection, follows project conventions, and gives later `update-tests` work something meaningful to improve.

## Core Steps

1. Determine the exact code or behavior under test.
2. Confirm there is no meaningful existing suite to improve.
3. Use the sibling [review-tests.md](review-tests.md) to identify the minimum high-signal coverage needed.
4. Choose the narrowest useful test layer.
5. Write the first meaningful tests with a bias toward behavioral signal over quantity.
6. Run the tests, confirm they fail when the behavior breaks, then re-run the sibling [review-tests.md](review-tests.md) if needed.

## Output

```markdown
## Test Creation Handoff

- Scope: <files, behavior, or function>
- Test layer: <unit / integration / component / e2e>
- Tests added or updated:
  - <file>
- Checks run:
  - <command>
- Remaining gaps:
  - <gap or none>
```
