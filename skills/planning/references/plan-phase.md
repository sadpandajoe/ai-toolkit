---
name: plan-phase
description: Plan only the next independently verifiable phase of a MULTI_PHASE unit — relevant files/patterns, changes, tests, and exit conditions — validated through the six-state gate contract instead of a numeric review threshold. Internal helper called once per phase by create-feature and any workflow iterating an accepted architecture decomposition. Do NOT use for the whole unit at once — that is decompose-work's job — or for SINGLE_PHASE/BATCHED work, which never reaches this file.
user-invocable: false
disable-model-invocation: true
---

# Plan Phase

Shared procedure for producing a small, just-in-time implementation plan for
exactly one phase of an accepted architecture decomposition, then gating it
through `rules/gates.md`'s six-state contract rather than a numeric
threshold.

This runs once per phase, called from the caller's per-phase loop —
never as a way to plan the whole `MULTI_PHASE` unit up front. Sibling
[decompose-work.md](decompose-work.md) already produced the phase boundaries,
ordering, and exit goals this file plans against; it does not re-derive them.

## When this runs

Only after `decompose-work.md`'s output reached `architecture_plan_status:
PASS` and the caller has selected the next phase in dependency order. Never
runs for `SINGLE_PHASE` or `BATCHED` work — those never produce a phase list.

## Inputs

The caller provides:

- **Phase**: which phase, and its exit goal from the architecture artifact
- **Global invariants**: the constraints every phase must preserve, from
  `decompose-work.md`'s output
- **Prior phase evidence**: what has actually landed so far, if this is not
  the first phase

## Procedure

### 1. Plan the phase

<!-- aitk-model-route:planning.plan-phase -->
Dispatch the `planner` subagent (per `rules/specialist-handoff.md`) in a
phase-plan-scoped task — the same worker `decompose-work.md` uses, in its
other mode. Output: relevant files/patterns, the changes this phase makes,
the tests that prove it, and this phase's own exit conditions. No plan
content for any later phase.

### 2. Apply the planning retry budget

Track this against `reasoning_attempts.phase_plan` (schema in
`aitk/size_axis.py`):

- Initial attempt plus one informed retry. A third normal full-plan round is
  not allowed.
- Editorial/completeness fixes (a missing file path, a test note, wording, a
  rollback note) may be patched without consuming the retry budget.
- Reasoning failures (an invalid architecture assumption, a disproven
  assumption, an incompatible contract, competing designs) consume it.
- After two reasoning failures, do not keep revising the same artifact —
  escalate the unresolved decision only, as a compact adjudication package.
- Escalation knob: increase one dimension at a time. More effort when depth
  is missing; change model when perspective is missing; the highest
  reasoning tier only once both prior approaches remain unresolved.

### 3. Validate the phase plan

Route to the Codex plan-validator contract (`agents/codex/plan-validator.md`)
in its `phase-plan` mode — never the `planner` that authored the plan;
`aitk.gates.assert_independent_verification("planner",
"codex-plan-validator")` is the machine-checkable slice of that rule.
Validates only this phase's plan, not the whole decomposition again.

### 4. Phase-size guard

If the next phase cannot be planned, implemented, and verified coherently —
even at this narrower scope — split it once more before implementation
proceeds, rather than forcing an oversized phase through.

### 5. Gate and record

Record the outcome as `phase_plan_status` using `aitk.gates`' six-state
vocabulary (`PASS`/`RETRY`/`ESCALATE`/`USER_DECISION`/`BLOCKED`/
`RECLASSIFY`) — never a numeric threshold, which this procedure replaces for
phase plans. Only proceed to implementing this phase once `phase_plan_status`
reaches `PASS`.

## Output

- This phase's plan (files/patterns, changes, tests, exit conditions)
- `phase_plan_status` gate outcome
- Updated `reasoning_attempts.phase_plan` count
- Any `RECLASSIFY`/`ESCALATE` adjudication package, if the retry budget was
  exhausted

Completed-phase checkpointing — recording what landed, any learned
constraints, global-invariant changes, and the verification evidence
pointer — happens after this phase is implemented and verified, in the
caller's per-phase loop, not here, using
[skills/reporting/templates/phase-handoff.md](../../reporting/templates/phase-handoff.md).

## Constraints

- Plan only the next phase. Do not draft ahead for phases whose
  dependencies have not landed yet.
- Do not let this phase's plan silently rewrite an accepted global
  invariant from `decompose-work.md`'s output — if new evidence requires
  that, return `RECLASSIFY`/`ESCALATE` and route back to `decompose-work.md`
  to update the architecture artifact explicitly.
- Do not create a second agent for phase planning — this reuses the same
  `planner` worker `decompose-work.md` dispatches, with a phase-scoped task.

## Notes

- `skills/goals/create-feature/SKILL.md`'s Multi-Phase Path routes every
  phase of a `MULTI_PHASE` unit through this file today, same as
  `decompose-work.md` — this is the live path, not a dual-run alongside the
  older reviewer-iterate-then-cold-read loop, which now runs only for
  `SINGLE_PHASE`/`BATCHED` callers via
  `skills/workflows/references/review-plan.md` (see
  `skills/planning/SKILL.md`'s Notes).
