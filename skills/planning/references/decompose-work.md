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
- **Delivery order**: the order phases land and what each leaves deployable;
  `bin/aitk deliver` commits and pushes each phase and opens or reuses the
  branch's one draft PR. Keep a single PR when a migration cannot ship ahead of
  its consumer or a contract must flip atomically.

Never turn BATCHED work into fake architectural phases; a repeated mechanical
operation is waves, not phases. Never cut phases as horizontal layers (all
models, then all APIs, then all UI): each phase is a vertical slice that leaves
the system working if deployed alone.

## Output

The decomposition is the `## Decomposition` section of `PLAN.md`: the Produce
items above, ending with the phase table as a fenced `phases-json` block, one
object per phase in delivery order:

```phases-json
[{"name":"<phase>","complexity":"STANDARD","size":"M","status":"pending"}]
```

A planner returns that section as text. The parent writes it to `PLAN.md`
verbatim and records the table by passing the block's content unchanged to
`bin/aitk project-state phases --phases-json '<block content>'`.

Then run validation in `decomposition` mode
([validate-plan.md](validate-plan.md)) before planning the first phase.
