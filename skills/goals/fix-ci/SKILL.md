---
name: fix-ci
description: Use when a CI build or check has failed and you want to diagnose and fix it. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md, and the full S/M/L/XL size axis under aitk/size_axis.py. Do NOT use for bug fixes unrelated to CI (skills/goals/fix-bug), feature work (skills/goals/create-feature), or refactors — this skill only fixes failing CI runs.
---

# Fix CI

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `fix-ci` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`,
`rules/specialist-handoff.md`, and `skills/review/references/sol-review.md`
first — they define the classification block, the fast-path rules, the
six-state gate contract, the input/output shape for every specialist
dispatch this skill uses, and the review procedure this skill's review step
delegates to. This skill is the v2 goal-skill entry point for CI failures,
implementing all three complexity tiers across every size and execution
shape.

## Scope

**In scope:** normalize the CI input, gather real failing log output,
classify the failure and its size; for TRIVIAL, apply the safe fix inline;
for STANDARD, investigate then implement via native specialists, with one
fresh reviewer before completion; for COMPLEX or a `BATCHED` shape, plan
first via a dedicated planner, then run the Standard Path per slice — one
slice per independent root cause when a run has more than one; verify and
record completion on every path.

**Out of scope:** anything that isn't a CI failure — bug fixes unrelated to
CI, feature work, and refactors belong to the relevant goal skill instead.

## Steps

1. Normalize the input: a GitHub Actions run URL, PR number, local log file,
   local zip artifact bundle, or no argument (resolve the latest failed run
   for the current branch).
2. Gather real failing log output per
   `skills/debug/references/ci-gather-logs.md`. Stop if no actual log output
   or artifact source can be resolved — never classify from a status string
   or dashboard state.
3. Classify the failure per
   `skills/debug/references/ci-classify-failure.md`. If the failure is
   Pre-existing/not-our-failure, exit early with the evidence — no fix or
   verification cycle. If multiple failures remain, group them by root cause
   per that reference's Group failures rule — one shared cause is one fix
   path; independent causes become the Complex Path's slices below.
4. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Certainty: Clear / Uncertain
   Reason: [one line]
   ```
5. Emit a Size Gate block, classifying against `aitk/size_axis.py`'s `size`
   enum and deriving `execution_shape`, per `skills/goals/create-feature/
   SKILL.md`'s Size Gate step (same block shape, same phaseability signal
   table, same `S`/`M` → `SINGLE_PHASE` default): a single-cause CI failure
   is `S`/`M` and stays `SINGLE_PHASE`; step 3's grouping into more than one
   independent root cause is the primary `BATCHED` signal — each root cause
   is a wave/item in the Complex Path's slice loop. Reserve `MULTI_PHASE` for
   the rare case where fixing the failure itself requires phased,
   architectural changes (e.g. a flaky test-infra overhaul), not merely
   several independent fixes. Persist `size`, `execution_shape`, and (if not
   `SINGLE_PHASE`) `phaseability_reason` on `PROJECT.md`'s frontmatter, same
   convention as `create-feature`. Branch on `execution_shape`:
   - `SINGLE_PHASE` → continue to step 6.
   - `BATCHED` → always follow the Complex Path (step 6 routes here
     regardless of complexity tier).
   - `MULTI_PHASE` → follow the Multi-Phase Path below instead of steps 6–9,
     reusing `create-feature`'s Multi-Phase Path structure with this
     skill's own dispatch boundaries (`fix-ci.investigate` /
     `fix-ci.implement` / `fix-ci.test-authoring` / `fix-ci.review`) and
     gate name `fix-ci-phase-<phase name>-verify`.
6. If the classification is `COMPLEX`, or certainty is `Uncertain` at any
   tier, or step 5's `execution_shape` is `BATCHED`: follow the Complex Path
   below instead of applying step 3's classification inline or using the
   Standard Path.
7. If `TRIVIAL` with certainty `Clear`: apply the fix produced by
   step 3's classification inline, per the Trivial Fast-Path rules in
   `rules/complexity-gate.md` — no subagent spawns for the fix itself, no
   formal planning phase. Skip to step 9.
8. If `STANDARD` with certainty `Clear`, follow the Standard Path
   below instead of applying step 3's classification inline.
9. For `TRIVIAL` and `STANDARD` only: verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-ci-verify`,
   running the closest local equivalent of the failing CI step as `command`
   — see `skills/debug/references/ci-verify-fix.md`'s STRONG standard for
   what "closest equivalent" means. Follow the loop's RETRY/ESCALATE
   handling exactly — one fix attempt on `RETRY`, stop and surface to the
   user on `ESCALATE`. `COMPLEX`/`BATCHED` skips this step — the Complex
   Path verifies per slice and goes straight to step 10.
10. On `PASS`: record a completion entry on `PROJECT.md` (including the size
    fields set at step 5) and summarize the fix for the user. A `PASS` gate
    is a checkpoint, not license to stop before this step — see
    `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 8 and 9 above, in place of applying step 3's
classification inline:

<!-- aitk-model-route:fix-ci.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to deepen the root-cause analysis beyond step 3's
   classification — reproduce the failure locally when possible, confirm the
   root cause, and check whether other failures in the group share it. If its
   Evidence summary shows the root cause is still ambiguous, cross-system, or
   the fix needs an architectural decision, emit `State: RECLASSIFY` toward
   `COMPLEX` (step 6 above) instead of continuing — do not push an unclear
   cause forward into implementation.

<!-- aitk-model-route:fix-ci.implement -->
2. Dispatch `implementation-worker` (Phase: implement), handing it
   debug-worker's evidence pointer and a Scope naming the failing surface's
   files. It writes the regression test first per `rules/implementation.md`'s
   Test-First Modes, then the minimal fix — keeping scope limited to the
   failing surface, per `skills/debug/references/ci-fix-orchestration.md`'s
   Apply Safe Fixes rule.

<!-- aitk-model-route:fix-ci.test-authoring -->
3. Dispatch `test-worker` separately only when investigation surfaced a
   test-coverage gap outside the fix's own regression coverage — not on
   every STANDARD fix.

<!-- aitk-model-route:fix-ci.review -->
4. After verification (step 9) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that implemented the fix reviews
   its own work). Do not restate its dispatch or findings-translation steps
   here; its own Gate and record step already emits the `rules/gates.md`
   six-state block this workflow branches on, and its own step 4 escalates to
   `delta-review.md` when triggered — no separate escalation step is needed
   here.

5. Only proceed to step 10 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 6 routes here —
because a single failure is genuinely ambiguous or architectural, because
step 3 grouped the run into more than one independent root cause, or because
step 5's `execution_shape` is `BATCHED`. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — implementation slices, or waves/items for a `BATCHED`
shape — never architecture-decomposition phases; those belong only to
`MULTI_PHASE`'s Multi-Phase Path below.

<!-- aitk-model-route:fix-ci.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it step 3's grouped failure list as Goal. It returns a plan
   decomposed into the smallest implementable slices — one per independent
   root cause when the run has more than one, ordered smallest/safest first
   per `skills/debug/references/ci-fix-orchestration.md`'s Group failures
   rule — each with entrance/exit criteria and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   investigate, implement, and optional test-authoring steps (steps 1–3)
   against that unit's scope; then verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-ci-verify`,
   scoped to that unit — follow its RETRY/ESCALATE handling exactly, same
   as step 9 above; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 4). This reuses the `fix-ci.investigate`
   / `fix-ci.implement` / `fix-ci.test-authoring` / `fix-ci.review`
   boundaries above per unit — it is a loop over the same dispatch sites,
   not new ones. Move to the next unit only once this unit's review Gate
   block reaches `PASS`. For a `BATCHED` shape specifically, also run one
   final aggregate verification against gate name `fix-ci-verify` after the
   last wave/item, before step 10 — per-wave verification alone does not
   confirm the waves compose correctly together.

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-ci.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) — dispatch native
   `deep-rca-worker` when `routed_subagent` is native for the provider,
   otherwise the Codex `rca` contract via `model-run` — and check the
   result against `skills/debug/references/review-rca.md`'s RCA Gate
   Evidence Checklist before treating it as ready for implementation.

4. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 9 above does not run again once the Complex Path is
   running. Only proceed to step 10 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).

## Multi-Phase Path

Runs in place of every other path when step 5's Size Gate derives
`execution_shape: MULTI_PHASE` — a CI failure whose fix genuinely requires
phased, architectural changes rather than several independent repairs.
Mirrors `skills/goals/create-feature/SKILL.md`'s Multi-Phase Path exactly,
substituting this skill's own dispatch boundaries and gate names:

1. Run `skills/planning/references/decompose-work.md` once for the whole
   failure. Its `architecture_plan_status` must reach `PASS` before
   continuing — on `RECLASSIFY`/`ESCALATE`, stop and surface it rather than
   guessing a phase list. Persist its architecture artifact per
   `create-feature`'s Multi-Phase Path step 1.

2. For each phase, in the decomposition's declared order, following
   `create-feature`'s Multi-Phase Path step 2 (a)–(f) exactly: hand-set
   `current_phase`; reclassify `phase_complexity`/`phase_size`/
   `phase_execution_shape` for that phase alone; run `plan-phase.md` to
   `phase_plan_status: PASS`; implement and verify via whichever path the
   phase's own `phase_execution_shape` selects — reusing
   `fix-ci.investigate` / `fix-ci.implement` / `fix-ci.test-authoring` /
   `fix-ci.review` — and verify against gate name
   `fix-ci-phase-<phase name>-verify`. On `RECLASSIFY`/`ESCALATE`, stop and
   surface rather than silently reordering phases.

3. Once every phase's gate reaches `PASS`, proceed to step 10 (completion),
   recording the full phase history.

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Certainty: Clear / Uncertain
Reason: [one line]
```
followed by the Size Gate block, the Phase Plan block (`COMPLEX` or
`BATCHED` only), the `verification-loop` Gate block(s) (every path — one per
phase for `MULTI_PHASE`), the review Gate block (every path except plain
`TRIVIAL`), then a short summary of the fix once every gate reaches `PASS`.

## Notes

- This skill is now the live dispatch target for natural-language "fix CI" /
  "CI failure" requests — Claude Code's own skill selection prefers this
  narrower description over the general `skills/workflows` router, same as
  `fix-bug`. The `interfaces/workflows.json` `fix-ci` entry now points its
  `reference` directly at this file; the standalone
  `skills/workflows/references/fix-ci.md` (pre-rename
  trivial/moderate/standard vocabulary; `aitk/checkpoint.py`'s `_contract()`
  never read its content) has been deleted.
