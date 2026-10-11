# Plan Implementation

The one plan shape, for STANDARD work, for each phase of MULTI_PHASE work, and
for a COMPLEX SINGLE_PHASE change. The parent writes it inline for STANDARD
work; for COMPLEX work the planner (`agents/specialists/planner.md`, on the
`planning` route in `phase-plan` mode) returns this same shape and the parent
writes it to `PLAN.md` verbatim.

## Phase plans

Plan exactly the next independently verifiable phase, and nothing about later
phases beyond honoring the accepted decomposition's contracts and invariants.
Reclassify the phase first: most phases of a COMPLEX project are STANDARD. A
STANDARD phase is planned inline; a COMPLEX phase goes to the planner. When the
phase trips the Phase-Size Guard in `skills/planning/SKILL.md`, split it once
and record the split in the phase table (`bin/aitk project-state phases`); do
not re-plan the whole project.

## What the plan settles

Plan from the accepted brief, ticket, RCA, or phase exit goal, and take the
narrowest approach that meets it; a broader one can follow later. Produce:

- the relevant files and the existing patterns to follow, as `file:line`;
- the changes, as slices only when there is more than one coherent unit, each
  with the fields below;
- the test-first mode (RED/GREEN regression test for a bug, acceptance test set
  for a feature) with its first failing test;
- the exit conditions and the exact acceptance command;
- the global invariants touched, and how each is preserved;
- any decision only the user can make.

## Output

```markdown
## Implementation Plan            # or ## Bug Fix Plan / ## Phase: <name>
Approach: <one line, and why it is the narrowest>
Root cause: <validated RCA>       # bugs only
Test-first: <RED/GREEN | acceptance set> — <first failing test>

### Slices
#### Slice 1: <name>
- Scope: <files and boundaries, with the patterns to follow as file:line>
- Depends on: <none | slice>
- Entrance: <what must be true first>
- Exit: <verifiable conditions>
- Acceptance: <exact command or assertion>

### Global invariants touched
- <invariant and how it is preserved, or none>

### Data or API implications
- <impact or none>

### Risks
- <risk>

### Decisions needed
- <user decision or none>
```

Write it to `PLAN.md` only when the work is COMPLEX, MULTI_PHASE, or spans
sessions; a STANDARD SINGLE_PHASE plan may live in `PROJECT.md` as action items.
A phase plan is appended to `PLAN.md` as `## Phase: <name>`, and the parent
marks the phase active:

```bash
bin/aitk project-state phase --name <phase> --status active
```

Validation follows the When list in [validate-plan.md](validate-plan.md).
Hand each unit to its worker with the input block in
`skills/reporting/templates/phase-handoff.md`.
