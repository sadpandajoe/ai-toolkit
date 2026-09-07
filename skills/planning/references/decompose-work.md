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
- **Delivery order**: one prepared commit per phase is the default; the
  roadmap states the order in which they land and what each leaves deployable.
  A phase is pushed and opened as its own PR only under the workflow's
  `publish-explicit` gate (authorization at intake with `--deliver-per-phase`
  or once at the first phase boundary); until then it is `prepared — awaiting
  publish authorization`. A whole-feature PR is an explicit opt-out recorded as
  `Delivery: single PR — <reason>` (a migration that cannot ship ahead of its
  consumer, a contract that must flip atomically).

Never turn BATCHED work into fake architectural phases; a repeated mechanical
operation is waves, not phases. Never cut phases as horizontal layers (all
models, then all APIs, then all UI): each phase is a vertical slice that leaves
the system working if deployed alone.

## Output

Write the decomposition to `PLAN.md` under `## Decomposition` and record the
phase table with:

```bash
bin/aitk project-state phases --phases-json '[{"name":"<phase>","complexity":"STANDARD","size":"M","status":"pending"}, ...]'
```

Then run validation in `decomposition` mode
([validate-plan.md](validate-plan.md)) before planning the first phase.
