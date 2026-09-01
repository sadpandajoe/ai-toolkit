---
name: fix-bug
description: Use when the user reports a bug, broken behavior, or asks to fix or diagnose something. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md, and the full S/M/L/XL size axis under aitk/size_axis.py. Do NOT use for feature work, refactors, or requests that aren't a bug fix — see skills/goals/create-feature or the relevant domain skill instead.
---

# Fix Bug

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`,
`rules/specialist-handoff.md`, and `skills/review/references/sol-review.md`
first — they define the classification block, the fast-path rules, the
six-state gate contract, the input/output shape for every specialist
dispatch this skill uses, and the review procedure the Standard/Complex/
Multi-Phase paths' review step delegates to. For an `L`/`XL` bug whose
Size Gate derives `MULTI_PHASE`, also read
`skills/planning/references/decompose-work.md` and `plan-phase.md` before
starting the Multi-Phase Path below. This skill is the v2 goal-skill entry
point for bug fixes, implementing all three complexity tiers across every
size and execution shape.

## Scope

**In scope:** classify the bug report's complexity and size; for TRIVIAL,
implement the fix inline; for STANDARD, investigate — validating the RCA
against an explicit gate — then implement via native specialists, with one
fresh reviewer before completion; for COMPLEX or a `BATCHED` shape, plan
first via a dedicated planner, then run the Standard Path per slice; for a
`MULTI_PHASE` shape, decompose then plan and execute per phase; verify and
record completion on every path.

**Out of scope:** feature work and refactors — this skill only fixes reported
bugs.

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
   table, same `S`/`M` → `SINGLE_PHASE` default): most bug fixes are `S`/`M`
   and stay `SINGLE_PHASE`; reserve `L`/`XL` for a bug whose fix genuinely
   spans independent, separately-verifiable units (a cross-cutting
   regression, a backport train of the same fix across many call sites, a
   root cause that itself decomposes into distinct repairs). Persist `size`,
   `execution_shape`, and (if not `SINGLE_PHASE`) `phaseability_reason` on
   `PROJECT.md`'s frontmatter, same convention as `create-feature`. Branch on
   `execution_shape`:
   - `SINGLE_PHASE` → continue to step 3.
   - `BATCHED` → always follow the Complex Path (step 3 routes here
     regardless of complexity tier — the per-slice loop already fits
     repetitive volume).
   - `MULTI_PHASE` → follow the Multi-Phase Path below instead of steps 3–7,
     reusing `create-feature`'s Multi-Phase Path structure with this
     skill's own dispatch boundaries (`fix-bug.investigate` /
     `fix-bug.implement` / `fix-bug.test-authoring` / `fix-bug.review`) and
     gate name `fix-bug-phase-<phase name>-verify`.
3. If the classification from step 1 is `COMPLEX`, or certainty is
   `Uncertain` at any tier, or step 2's `execution_shape` is `BATCHED`:
   follow the Complex Path below instead of implementing inline or using the
   Standard Path.
4. If `TRIVIAL` with certainty `Clear`: implement the fix inline, per
   the Trivial Fast-Path rules in `rules/complexity-gate.md` — no subagent
   spawns for the implementation itself, no formal planning phase. Skip to
   step 6.
5. If `STANDARD` with certainty `Clear`, follow the Standard Path
   below instead of implementing inline.
6. For `TRIVIAL` and `STANDARD` only: verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-bug-verify`.
   Follow its RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`,
   stop and surface to the user on `ESCALATE`. `COMPLEX`/`BATCHED` skips this
   step — the Complex Path verifies per slice and goes straight to step 7.
7. On `PASS`: record a completion entry on `PROJECT.md` (including the size
   fields set at step 2) and summarize the fix for the user. A `PASS` gate is
   a checkpoint, not license to stop before this step — see
   `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 5 and 6 above, in place of inline implementation:

<!-- aitk-model-route:fix-bug.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to reproduce the bug and identify root cause. If its Evidence
   summary shows the root cause is still ambiguous, cross-system, or the fix
   needs an architectural decision, emit `State: RECLASSIFY` toward `COMPLEX`
   (step 3 above) instead of continuing — do not push an unclear cause
   forward into implementation.

2. Check debug-worker's evidence against
   `skills/debug/references/review-rca.md`'s RCA Gate Evidence Checklist and
   emit its Gate block explicitly, under gate name `fix-bug-rca`: all six
   checklist items evidenced is `PASS`; a missing item is `RETRY` (re-dispatch
   step 1 with the gap named); the same item still missing on the next
   attempt is `ESCALATE` per `rules/gates.md`'s Repeat-Failure Counting Rule.
   Do not start step 3 before this gate reaches `PASS` — this is the explicit
   check the ambiguity language in step 1 only gestures at.

<!-- aitk-model-route:fix-bug.implement -->
3. Dispatch `implementation-worker` (Phase: implement), handing it
   debug-worker's evidence pointer and a Scope naming the files the fix may
   touch. It writes the regression test first per `rules/implementation.md`'s
   Test-First Modes, then the minimal fix.

<!-- aitk-model-route:fix-bug.test-authoring -->
4. Dispatch `test-worker` separately only when investigation surfaced a
   test-coverage gap outside the fix's own regression test — not on every
   STANDARD fix.

<!-- aitk-model-route:fix-bug.review -->
5. After verification (step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that implemented the fix reviews
   its own work). Do not restate its dispatch or findings-translation steps
   here; its own Gate and record step already emits the `rules/gates.md`
   six-state block this workflow branches on, and its own step 4 escalates to
   `delta-review.md` when triggered — no separate escalation step is needed
   here.

6. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here —
for a `COMPLEX`/low-confidence `SINGLE_PHASE` bug, or for any `BATCHED`
shape regardless of complexity tier. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — implementation slices for a `SINGLE_PHASE` bug, or
waves/items for a `BATCHED` one — never architecture-decomposition phases;
those belong only to `MULTI_PHASE`'s Multi-Phase Path below.

<!-- aitk-model-route:fix-bug.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the bug report as Goal. It returns a plan decomposed
   into the smallest implementable slices, each with entrance/exit criteria
   and a scope boundary, per `skills/implement-change/SKILL.md`'s Slice
   Awareness section. Never implement from an unreviewed plan the planner
   itself approved — the planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   investigate, RCA-gate, implement, and optional test-authoring steps
   (steps 1–4) against that unit's scope; then verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-bug-verify`,
   scoped to that unit — follow its RETRY/ESCALATE handling exactly, same
   as step 6 above; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 5). This reuses the `fix-bug.investigate`
   / `fix-bug.implement` / `fix-bug.test-authoring` / `fix-bug.review`
   boundaries above per unit — it is a loop over the same dispatch sites,
   not new ones. Move to the next unit only once this unit's review Gate
   block reaches `PASS`. For a `BATCHED` shape specifically, follow
   `skills/verification-loop/SKILL.md`'s BATCHED shape subsection: after the
   last wave/item, before step 7, run the AGGREGATE verification against its
   own gate name (`fix-bug-verify-aggregate`, never reusing a wave's
   `fix-bug-verify` history).

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-bug.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) before running
   step 2's RCA gate against `skills/debug/references/review-rca.md`'s
   checklist.

4. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 6 above does not run again once the Complex Path is
   running. Only proceed to step 7 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).

## Multi-Phase Path

Runs in place of every other path when step 2's Size Gate derives
`execution_shape: MULTI_PHASE` — a bug whose root cause and fix genuinely
decompose into distinct, independently-verifiable repairs. Mirrors
`skills/goals/create-feature/SKILL.md`'s Multi-Phase Path exactly, substituting
this skill's own dispatch boundaries and gate names:

1. Run `skills/planning/references/decompose-work.md` once for the whole bug.
   Its `architecture_plan_status` must reach `PASS` before continuing — on
   `RECLASSIFY`/`ESCALATE`, stop and surface it rather than guessing a phase
   list. Persist its architecture artifact per `create-feature`'s Multi-Phase
   Path step 1.

2. For each phase, in the decomposition's declared order, following
   `create-feature`'s Multi-Phase Path step 2 (a)–(f) exactly: hand-set
   `current_phase`; reclassify `phase_complexity`/`phase_size`/
   `phase_execution_shape` for that phase alone; run `plan-phase.md` to
   `phase_plan_status: PASS`; implement and verify via whichever path the
   phase's own `phase_execution_shape` selects — reusing
   `fix-bug.investigate` / `fix-bug.implement` / `fix-bug.test-authoring` /
   `fix-bug.review`, including the Standard Path's RCA gate for any phase
   that runs it — and verify against gate name
   `fix-bug-phase-<phase name>-verify`. On `RECLASSIFY`/`ESCALATE`, stop and
   surface rather than silently reordering phases.

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
`BATCHED` only), the RCA Gate block (`STANDARD`, and any `COMPLEX`/
`MULTI_PHASE` unit that runs the Standard Path), the `verification-loop`
Gate block(s) (every path — one per phase for `MULTI_PHASE`), the review
Gate block (every path except plain `TRIVIAL`), then a short summary of the
fix once every gate reaches `PASS`.

## Notes

- This skill is now the live dispatch target for natural-language "fix bug" /
  "diagnose" / "broken behavior" requests — Claude Code's own skill selection
  prefers this narrower description over the general `skills/workflows`
  router. `skills/workflows/references/fix-bug.md` and its
  `interfaces/workflows.json` entry stay in place indefinitely as
  durable-contract infrastructure for literal `fix-bug`-command-name
  compatibility (`aitk/checkpoint.py`'s `_contract()` cross-validates against
  both regardless of which skill dispatches it — confirmed empirically when
  deleting the entry broke checkpoint, contract, and model-routing tests) —
  they are not deleted by this retrofit and stay on the pre-rename
  TRIVIAL/MODERATE/STANDARD vocabulary.
