---
name: plan-implementation
description: Produce a compact slice-based implementation plan for STANDARD work or one phase, with scope, entrance/exit/acceptance, and the test-first mode the implementer will use. Internal helper.
user-invocable: false
disable-model-invocation: true
---

# Plan Implementation

The compact plan shape for STANDARD work and for individual phases. The parent
usually writes it inline; the `planning` route returns the same shape for
COMPLEX phases.

## Steps

1. State the input: the accepted brief, ticket, RCA, or phase exit goal.
2. Choose the narrowest workable approach; a broader one can follow later.
3. Split into slices only when there is more than one coherent unit. Each
   slice: scope (files, boundaries, what it does not touch), depends on,
   entrance criteria, exit criteria, acceptance (command or assertion).
4. Name the test-first mode: RED/GREEN regression test for a bug, acceptance
   test set for a feature, with the first failing test.
5. Call out data or API implications, risks, and any decision only the user
   can make.

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
