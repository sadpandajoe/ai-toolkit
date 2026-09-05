# Plan Phase

Plan exactly the next independently verifiable phase (or a COMPLEX
SINGLE_PHASE change). Nothing about later phases beyond honoring the accepted
decomposition's contracts and invariants.

## Who runs it

Reclassify the phase first: most phases of a COMPLEX project are STANDARD.
STANDARD phase: the parent plans inline using the slice shape in
[plan-implementation.md](plan-implementation.md). COMPLEX phase: the `planning`
route in `phase-plan` mode, through the goal workflow's planning boundary.

## Produce

- Relevant files and the existing patterns to follow (grep for them).
- The changes, as slices when the phase has more than one coherent unit.
- Tests: the RED/GREEN regression test (bug) or the acceptance test set
  (feature) that proves the phase.
- Exit conditions and the exact acceptance command.
- Any global invariant this phase touches, and confirmation it is preserved.

## Phase-size guard

If the phase cannot be planned, implemented, and verified coherently as one
unit, split it once more and record the split in the phase table
(`bin/aitk project-state phases`). Do not re-plan the whole project.

## Output

Append `## Phase: <name>` to `PLAN.md` and mark the phase `active`:

```bash
bin/aitk project-state phase --name <phase> --status active
```

COMPLEX phase plans run validation in `phase-plan` mode
([validate-plan.md](validate-plan.md)). STANDARD phase plans go straight to
implementation; the verification loop is their gate.
