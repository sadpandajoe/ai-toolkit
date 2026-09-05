# Decompose Work

Use only when the routing snapshot says `MULTI_PHASE`. Produces the
architecture-level decomposition; detailed planning happens per phase, just in
time, after the previous phase is verified.

## Who runs it

COMPLEX work: the `planning` route in `decomposition` mode, through the goal
workflow's planning boundary. STANDARD/XL work: the parent may decompose inline
when the boundaries are obvious; otherwise use the same route.

## Inputs

The accepted brief or ticket, the phaseability reason from the snapshot,
known constraints, and any existing architecture notes in `PROJECT.md`.

## Produce

- **Boundaries**: the independently useful capabilities or workstreams, each
  with what it owns and what it must not touch.
- **Contracts and dependencies**: interfaces between phases, ordering, what
  later phases may assume from earlier ones.
- **Global invariants**: the properties every phase must preserve (data
  compatibility, public API stability, security posture).
- **Risks**: where learning from an early phase is likely to change later ones.
- **Per-phase exit goal**: one observable outcome per phase, plus its size and
  provisional complexity. No file lists or step lists for later phases.

Never turn BATCHED work into fake architectural phases; a repeated mechanical
operation is waves, not phases.

## Output

Write the decomposition to `PLAN.md` under `## Decomposition` and record the
phase table with:

```bash
bin/aitk project-state phases --phases-json '[{"name":"<phase>","complexity":"STANDARD","size":"M","status":"pending"}, ...]'
```

Then run validation in `decomposition` mode
([validate-plan.md](validate-plan.md)) before planning the first phase.
