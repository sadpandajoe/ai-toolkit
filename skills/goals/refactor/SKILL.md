---
name: refactor
description: Use when the user asks to refactor, restructure, simplify, clean up, or extract/rename code without changing observable behavior. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md, and the full S/M/L/XL size axis under aitk/size_axis.py. Do NOT use for bug fixes (skills/goals/fix-bug) or feature work that changes behavior (skills/goals/create-feature) — this skill only reshapes code that must keep behaving the same way.
---

# Refactor

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `refactor` entry
in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, `rules/specialist-handoff.md`,
and `skills/review/references/sol-review.md` first — they define the
classification block, the fast-path rules, the six-state gate contract, the
input/output shape for every specialist dispatch this skill uses, and the
review procedure this skill's review step delegates to. For an `L`/`XL`
refactor whose Size Gate derives `MULTI_PHASE`, also read
`skills/planning/references/decompose-work.md` and `plan-phase.md` before
starting the Multi-Phase Path below.

## Scope

**In scope:** classify the refactor request's complexity and size; establish
the invariants (existing behavior) the refactor must preserve; perform the
refactor via native specialists; verify equivalence against those invariants;
one fresh reviewer before completion.

**Out of scope:** bug fixes and behavior-changing feature work — if the
requested change would alter observable behavior, redirect to
`skills/goals/fix-bug` or `skills/goals/create-feature` instead of forcing it
through this skill's equivalence gate.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Certainty: Clear / Uncertain
   Reason: [one line]
   ```
2. Emit a Size Gate block, classifying against `aitk/size_axis.py`'s `size`
   enum and deriving `execution_shape`, per `skills/goals/create-feature/
   SKILL.md`'s Size Gate step (same block shape, same phaseability signal
   table, same `S`/`M` → `SINGLE_PHASE` default): most refactors are `S`/`M`
   and stay `SINGLE_PHASE`; reserve `L`/`XL` for a refactor that genuinely
   spans independent, separately-verifiable units (a rename that fans out
   across many call sites in batches, a layered extraction that only makes
   sense done one layer at a time). Persist `size`, `execution_shape`, and
   (if not `SINGLE_PHASE`) `phaseability_reason` on `PROJECT.md`'s
   frontmatter, same convention as `create-feature`. Branch on
   `execution_shape`:
   - `SINGLE_PHASE` → continue to step 3.
   - `BATCHED` → always follow the Complex Path (step 3 routes here
     regardless of complexity tier — the per-slice loop already fits
     repetitive volume).
   - `MULTI_PHASE` → follow the Multi-Phase Path below instead of steps 3–7,
     reusing `create-feature`'s Multi-Phase Path structure with this skill's
     own dispatch boundaries (`refactor.invariants` / `refactor.implement` /
     `refactor.review`) and gate name `refactor-phase-<phase name>-verify`.
3. If the classification from step 1 is `COMPLEX`, or certainty is
   `Uncertain` at any tier, or step 2's `execution_shape` is `BATCHED`:
   follow the Complex Path below instead of implementing inline or using the
   Standard Path.
4. If `TRIVIAL` with certainty `Clear`: perform the refactor inline,
   per the Trivial Fast-Path rules in `rules/complexity-gate.md` — no
   subagent spawns for the refactor itself, no formal planning phase. State
   the invariant informally (e.g. "existing test file X covers this,
   unchanged") before editing. Skip to step 6.
5. If `STANDARD` with certainty `Clear`, follow the Standard Path
   below instead of refactoring inline.
6. For `TRIVIAL` and `STANDARD` only: verify equivalence using
   `skills/verification-loop/SKILL.md` against gate name `refactor-verify`,
   with `required_criteria` set to the invariants established in the
   Standard Path's step 1 (or the informal invariant from step 4 for
   `TRIVIAL`) — the same tests/behavior checks that passed before the
   refactor must still pass after it, unchanged in what they assert. Follow
   its RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`, stop
   and surface to the user on `ESCALATE`. `COMPLEX`/`BATCHED` skips this
   step — the Complex Path verifies per slice and goes straight to step 7.
7. On `PASS`: record a completion entry on `PROJECT.md` (including the size
   fields set at step 2) and summarize the refactor for the user. A `PASS`
   gate is a checkpoint, not license to stop before this step — see
   `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 5 and 6 above, in place of inline refactoring: establish
invariants with `debug-worker`, gate them, implement with a native
specialist, then review. Registers dispatch boundaries `refactor.invariants`
/ `refactor.implement` / `refactor.review`.

→ Full procedure: [references/standard-path.md](references/standard-path.md)

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here —
for a `COMPLEX`/low-confidence `SINGLE_PHASE` refactor, or for any `BATCHED`
shape regardless of complexity tier. Plans via a dedicated `planner`, then
runs the Standard Path per slice or wave/item. Registers dispatch boundary
`refactor.plan`.

→ Full procedure: [references/complex-path.md](references/complex-path.md)

## Multi-Phase Path

Runs in place of every other path when step 2's Size Gate derives
`execution_shape: MULTI_PHASE`. Mirrors `create-feature`'s Multi-Phase Path,
decomposing then planning and executing per phase with this skill's own
dispatch boundaries and gate names.

→ Full procedure: [references/multi-phase-path.md](references/multi-phase-path.md)

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Certainty: Clear / Uncertain
Reason: [one line]
```
followed by the Size Gate block, the Phase Plan block (`COMPLEX` or
`BATCHED` only), the Invariants Gate block (`STANDARD`, and any `COMPLEX`/
`MULTI_PHASE` unit that runs the Standard Path), the `verification-loop`
Gate block(s) (every path — one per phase for `MULTI_PHASE`), the review
Gate block (every path except plain `TRIVIAL`), then a short summary of the
refactor once every gate reaches `PASS`.

## Notes

- This skill's equivalence gate is behavioral, not textual — a refactor that
  changes an invariant's assertions (not just its implementation) has
  drifted into a behavior change and belongs in `fix-bug` or `create-feature`
  instead. `RECLASSIFY` toward those skills rather than loosening the
  invariant to fit.
