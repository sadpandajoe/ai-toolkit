---
name: decompose-work
description: Produce an architecture decomposition for MULTI_PHASE work — boundaries, dependencies, ordering, global invariants, risks, and phase exit goals, with no detailed code plan for any phase but the first. Internal helper called by create-feature and any workflow whose execution_shape is MULTI_PHASE. Do NOT use for SINGLE_PHASE or BATCHED work — a BATCHED workload never gets fake architectural phases.
user-invocable: false
disable-model-invocation: true
---

# Decompose Work

Shared procedure for turning a `MULTI_PHASE` unit of work into a validated
architecture decomposition, before any phase is planned or implemented.

This is a leaf capability, not a loop: it runs once per architecture
decision (and again only on `RECLASSIFY`/`ESCALATE`, never as routine
iteration). Planning the next individual phase in detail is sibling
[plan-phase.md](plan-phase.md)'s job, not this one's.

## When this runs

Only when the caller's size-axis classification (`aitk.size_axis`) derived
`execution_shape: MULTI_PHASE`. `SINGLE_PHASE` work skips this file
entirely; `BATCHED` work never invokes it either — a repetitive/mechanical
workload gets waves, not architectural phases.

## Inputs

The caller provides:

- **Goal**: the feature or change being decomposed
- **Complexity and size**: the classification that produced `MULTI_PHASE`
- **Phaseability reason**: why this unit needs decomposition rather than a
  single phase (persisted as `phaseability_reason`)

## Procedure

### 1. Produce the decomposition

<!-- aitk-model-route:planning.decompose-work -->
Dispatch the `planner` subagent (per `rules/specialist-handoff.md`) in a
decomposition-scoped task — the same Opus worker used for `COMPLEX` plans,
not a separate agent. Its output names, for the whole unit:

- **Architecture boundaries** — the independently verifiable units
- **Dependencies and ordering** — which boundaries must land before which
- **Global invariants** — constraints every phase must preserve
- **Risks** — what could force a later re-decomposition
- **Phase exit goals** — one per boundary, not implementation detail

No phase beyond the first gets a detailed code plan here — that is
deferred to [plan-phase.md](plan-phase.md), run just-in-time per phase.

### 2. Validate the decomposition

Route to the Codex plan-validator contract (`agents/codex/plan-validator.md`)
in its `decomposition` mode — never the `planner` that authored the
decomposition; `aitk.gates.assert_independent_verification("planner",
"codex-plan-validator")` is the machine-checkable slice of that rule. SOL
validates boundaries, contracts, and dependencies only — not code-level
detail, since none exists yet at this stage. One informed revision on a
real finding, then adjudicate or escalate if substantive disagreement
remains; do not iterate past that.

### 3. Persist and gate

Record the decomposition outcome as `architecture_plan_status` using
`aitk.gates`' six-state vocabulary (`PASS`/`RETRY`/`ESCALATE`/
`USER_DECISION`/`BLOCKED`/`RECLASSIFY`), alongside the size-axis fields
already classified (`size`, `execution_shape`, `phaseability_reason`) —
schema in `aitk/size_axis.py`. Only proceed to per-phase planning once
`architecture_plan_status` reaches `PASS`.

## Output

- The architecture artifact (boundaries, dependencies, ordering, invariants,
  risks, phase exit goals)
- `architecture_plan_status` gate outcome
- Any `RECLASSIFY`/`ESCALATE` reason, if validation surfaced one

## Constraints

- Never turn a `BATCHED` workload into fake architectural phases — if the
  work is repetitive/mechanical, it does not belong in this procedure.
- Never let a later phase plan silently rewrite the accepted global
  architecture. If new evidence changes a global invariant while planning
  or implementing a phase, return `RECLASSIFY`/`ESCALATE` and explicitly
  update this artifact — do not patch it implicitly.
- Do not create a second agent for decomposition — this reuses the same
  `planner` worker `plan-implementation.md`'s `COMPLEX` path dispatches,
  with a decomposition-scoped task instead of a full plan.
- This procedure does not own phase-by-phase verification. Once a phase is
  planned and implemented, `verification-loop` evaluates it against that
  phase's own exit conditions.

## Notes

- `skills/goals/create-feature/SKILL.md`'s Multi-Phase Path routes every
  `MULTI_PHASE` unit through this file today — this is the live path, not a
  dual-run alongside the older reviewer-iterate-then-cold-read loop. That
  loop's 8/10-threshold approach now runs only for `SINGLE_PHASE`/`BATCHED`
  callers, via `skills/workflows/references/review-plan.md` steps 2–4 (see
  `skills/planning/SKILL.md`'s Notes).
- Persistence for the size-axis fields this procedure reads and writes was
  added in `aitk/size_axis.py` and `PROJECT_TEMPLATE.md`'s v2 frontmatter,
  ahead of this file, since a validator has to exist before anything can be
  checked against it.
