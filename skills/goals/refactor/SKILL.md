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

Runs between steps 5 and 6 above, in place of inline refactoring:

<!-- aitk-model-route:refactor.invariants -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to establish the invariants this refactor must preserve:
   the existing tests, contracts, or observable behavior that must read
   identically before and after. If no existing test coverage exercises the
   scope, its Evidence summary must say so explicitly — that gap becomes a
   `required_criteria` entry for step 6's verification (write the missing
   characterization test first, then refactor), not a silent assumption. If
   the scope's current behavior is itself ambiguous or contested, emit
   `State: RECLASSIFY` toward `COMPLEX` (step 3 above) instead of continuing
   — do not refactor against an invariant nobody actually agreed to.

2. Check the invariant evidence against a minimal checklist — behavior
   named, existing coverage identified (or its absence flagged), scope
   boundary named — and emit its Gate block explicitly, under gate name
   `refactor-invariants`: all three items evidenced is `PASS`; a missing
   item is `RETRY` (re-dispatch step 1 with the gap named); the same item
   still missing on the next attempt is `ESCALATE` per `rules/gates.md`'s
   Repeat-Failure Counting Rule. Do not start step 3 before this gate
   reaches `PASS`.

<!-- aitk-model-route:refactor.implement -->
3. Dispatch `implementation-worker` (Phase: implement), handing it the
   invariant evidence pointer and a Scope naming the files the refactor may
   touch. It performs the restructuring without changing the invariants'
   observable behavior — no new features, no bug fixes folded in, per
   `rules/implementation.md`.

<!-- aitk-model-route:refactor.review -->
4. After verification (step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that performed the refactor
   reviews its own work). Do not restate its dispatch or findings-
   translation steps here; its own Gate and record step already emits the
   `rules/gates.md` six-state block this workflow branches on, and its own
   step 4 escalates to `delta-review.md` when triggered — no separate
   escalation step is needed here.

5. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here —
for a `COMPLEX`/low-confidence `SINGLE_PHASE` refactor, or for any `BATCHED`
shape regardless of complexity tier. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — refactor slices for a `SINGLE_PHASE` change, or
waves/items for a `BATCHED` one — never architecture-decomposition phases;
those belong only to `MULTI_PHASE`'s Multi-Phase Path below.

<!-- aitk-model-route:refactor.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the refactor request as Goal. It returns a plan
   decomposed into the smallest independently-verifiable slices, each with
   its own invariant, entrance/exit criteria, and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   invariants, invariants-gate, and implement steps (steps 1–3) against that
   unit's scope; then verify equivalence using
   `skills/verification-loop/SKILL.md` against gate name `refactor-verify`,
   scoped to that unit — follow its RETRY/ESCALATE handling exactly, same
   as step 6 above; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 4). This reuses the `refactor.invariants`
   / `refactor.implement` / `refactor.review` boundaries above per unit — it
   is a loop over the same dispatch sites, not new ones. Move to the next
   unit only once this unit's review Gate block reaches `PASS`. For a
   `BATCHED` shape specifically, also run one final aggregate verification
   against gate name `refactor-verify` after the last wave/item, before
   step 7 — per-wave verification alone does not confirm the waves compose
   correctly together.

3. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 6 above does not run again once the Complex Path is
   running. Only proceed to step 7 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).

## Multi-Phase Path

Runs in place of every other path when step 2's Size Gate derives
`execution_shape: MULTI_PHASE` — a refactor whose scope genuinely decomposes
into distinct, independently-verifiable restructurings. Mirrors
`skills/goals/create-feature/SKILL.md`'s Multi-Phase Path exactly,
substituting this skill's own dispatch boundaries and gate names:

1. Run `skills/planning/references/decompose-work.md` once for the whole
   refactor. Its `architecture_plan_status` must reach `PASS` before
   continuing — on `RECLASSIFY`/`ESCALATE`, stop and surface it rather than
   guessing a phase list. Persist its architecture artifact per
   `create-feature`'s Multi-Phase Path step 1.

2. For each phase, in the decomposition's declared order, following
   `create-feature`'s Multi-Phase Path step 2 (a)–(f) exactly: hand-set
   `current_phase`; reclassify `phase_complexity`/`phase_size`/
   `phase_execution_shape` for that phase alone; run `plan-phase.md` to
   `phase_plan_status: PASS`; implement and verify via whichever path the
   phase's own `phase_execution_shape` selects — reusing
   `refactor.invariants` / `refactor.implement` / `refactor.review`,
   including the Standard Path's invariants gate for any phase that runs it
   — and verify against gate name `refactor-phase-<phase name>-verify`. On
   `RECLASSIFY`/`ESCALATE`, stop and surface rather than silently reordering
   phases.

3. Once every phase's gate reaches `PASS`, proceed to step 7 (completion),
   recording the full phase history.

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
