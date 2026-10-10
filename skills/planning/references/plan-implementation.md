# Plan Implementation

The compact plan shape for STANDARD work and for individual phases. The parent
usually writes it inline; the `planning` route returns the same shape for
COMPLEX phases.

## What the plan settles

Plan from the accepted brief, ticket, RCA, or phase exit goal, and take the
narrowest approach that meets it; a broader one can follow later. Split into
slices only when there is more than one coherent unit, and give each slice the
fields below. Name the test-first mode (RED/GREEN regression test for a bug,
acceptance test set for a feature) with its first failing test, and raise any
decision only the user can make.

## Output

```markdown
## Implementation Plan            # or ## Bug Fix Plan / ## Phase: <name>
Approach: <one line, and why it is the narrowest>
Root cause: <validated RCA>       # bugs only
Test-first: <RED/GREEN | acceptance set> — <first failing test>

### Slices
#### Slice 1: <name>
- Scope: <files and boundaries>
- Depends on: <none | slice>
- Entrance: <what must be true first>
- Exit: <verifiable conditions>
- Acceptance: <exact command or assertion>

### Data or API implications
- <impact or none>

### Risks
- <risk>

### Decisions needed
- <user decision or none>
```

Write it to `PLAN.md` only when the work is COMPLEX, MULTI_PHASE, or spans
sessions; a STANDARD SINGLE_PHASE plan may live in `PROJECT.md` as action items.
