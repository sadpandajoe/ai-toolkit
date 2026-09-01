---
name: create-feature
description: Use when the user asks to build, add, or implement a new feature or capability. Covers the full S/M/L/XL size axis and its derived SINGLE_PHASE/BATCHED/MULTI_PHASE execution shapes under rules/complexity-gate.md and aitk/size_axis.py. Do NOT use for bug fixes (skills/goals/fix-bug).
---

# Create Feature

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `create-feature`
entry in `interfaces/contracts.json`; use `bin/aitk checkpoint` for every
durable transition and effect record.

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`,
`rules/specialist-handoff.md`, and `skills/review/references/sol-review.md`
first — they define the classification block, the fast-path rules, the
six-state gate contract, the input/output shape for every specialist
dispatch this skill uses, and the review procedure this skill's review step
delegates to. For `MULTI_PHASE` work, also
read `skills/planning/references/decompose-work.md` and `plan-phase.md`
before starting the Multi-Phase Path below. This skill is the v2 goal-skill
entry point for new-feature requests, across every size and execution
shape.

## Scope

**In scope:** classify complexity (`rules/complexity-gate.md`) and size
(`aitk/size_axis.py`'s `S`/`M`/`L`/`XL`) for a feature request; derive
`execution_shape` from size, complexity, and — for `L`/`XL` — an inline
phaseability check; implement via whichever path that shape selects:
`SINGLE_PHASE` plans just-in-time and implements via the Trivial/Standard/
Complex path per `rules/complexity-gate.md`, the same structure
`skills/goals/fix-bug` uses for bug fixes; `BATCHED` reuses the Complex
Path's per-slice loop, generalized to waves/items; `MULTI_PHASE` runs
`skills/planning/references/decompose-work.md` once, then `plan-phase.md`
just-in-time per phase. Verify and record completion in every case.

**Out of scope (this commit):** enforcing never-self-verify specifically for
planner output (a later commit extends `aitk.gates`'s tests for it) and the
dual-run router pointer that makes this skill a live dispatch target — see
Notes.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Certainty: Clear / Uncertain
   Reason: [one line]
   ```
2. Emit a Size Gate block, classifying against `aitk/size_axis.py`'s `size`
   enum and deriving `execution_shape`:
   ```markdown
   ## Size Gate
   Size: S / M / L / XL
   Execution shape: SINGLE_PHASE / BATCHED / MULTI_PHASE
   Reason: [one line]
   ```
   - `S`/`M` default `SINGLE_PHASE` — do not decompose unless independently
     verifiable behavioral phases are already obvious.
   - `L` always runs the phaseability check below, inline, with no
     specialist dispatch. Choose `MULTI_PHASE` only when at least two
     independently verifiable units exist with meaningful dependencies or
     learning between them; choose `BATCHED` for repetitive/mechanical
     volume; otherwise stay `SINGLE_PHASE`.
   - `XL` defaults `MULTI_PHASE` (context and coordination risk are high);
     use `BATCHED` only for a highly repetitive/mechanical workload (e.g. a
     codemod or backport train).

   Phaseability signal table (guidance, not hard limits):

   | Signal | `SINGLE_PHASE` leaning | `BATCHED` leaning | `MULTI_PHASE` leaning |
   |---|---|---|---|
   | Work pattern | One coherent behavior/change | Same mechanical operation repeated | Different capabilities/workstreams |
   | Dependencies | Tightly coupled; splitting adds ceremony | Mostly independent, order-insensitive | Explicit ordering/dependency graph |
   | Learning | Later steps unlikely to change | Little reasoning; throughput is the issue | Early results may change later plans |
   | Verification | One meaningful end-state test | Same check repeated per wave/item | Each phase has distinct exit criteria |
   | Architecture | One accepted approach | No new architecture; known pattern repeats | Different boundaries/contracts must be established |
   | Context | Fits one bounded worker | Too many repeated items for one worker | Different contexts should be isolated by phase |

   Persist `size`, `execution_shape`, and (if not `SINGLE_PHASE`)
   `phaseability_reason` directly on `PROJECT.md`'s frontmatter — these
   fields are hand-set classification state, the same way `workflow` and
   `complexity` already are; `aitk/size_axis.py` validates the shape, it does
   not own writing it. Branch on `execution_shape`:
   - `SINGLE_PHASE` → continue to step 3.
   - `BATCHED` → always follow the Complex Path (step 3 routes here
     regardless of complexity tier for a `BATCHED` shape — the loop shape
     fits repetitive volume regardless of reasoning difficulty).
   - `MULTI_PHASE` → follow the Multi-Phase Path below instead of steps
     3–7.
3. If the classification from step 1 is `COMPLEX`, or certainty is
   `Uncertain` at any tier, or step 2's `execution_shape` is `BATCHED`:
   follow the Complex Path below instead of implementing inline or using the
   Standard Path.
4. If `TRIVIAL` with certainty `Clear`: implement the feature
   inline, per the Trivial Fast-Path rules in `rules/complexity-gate.md` — no
   subagent spawns for the implementation itself, no formal planning phase.
   Skip to step 6.
5. If `STANDARD` with certainty `Clear`, follow the Standard Path
   below instead of implementing inline.
6. For `TRIVIAL` and `STANDARD` only: verify using
   `skills/verification-loop/SKILL.md` against gate name
   `create-feature-verify`. Follow its RETRY/ESCALATE handling exactly — one
   fix attempt on `RETRY`, stop and surface to the user on `ESCALATE`.
   `COMPLEX` skips this step — the Complex Path verifies per slice and goes
   straight to step 7.
7. On `PASS`: record a completion entry on `PROJECT.md` (including the size
   fields set at step 2) and summarize the feature for the user. A `PASS`
   gate is a checkpoint, not license to stop before this step — see
   `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 5 and 6 above, in place of inline implementation. Unlike
`fix-bug`, there is no root-cause investigation phase — a feature request
starts from what the user described, not a symptom. Survey existing patterns
to follow inline, as the orchestrator (`rules/complexity-gate.md`'s Standard
Path already allows inline investigation/planning at this tier); no
specialist dispatch for the survey itself.

<!-- aitk-model-route:create-feature.implement -->
1. Dispatch `implementation-worker` per `rules/specialist-handoff.md` (Phase:
   implement), handing it the feature request, the surveyed pattern to
   follow, and a Scope naming the files it may touch. It writes tests first
   per `rules/implementation.md`'s Test-First Modes, then the feature code.

<!-- aitk-model-route:create-feature.test-authoring -->
2. Dispatch `test-worker` separately only when the feature needs coverage
   beyond the implementation worker's own tests (e.g. a new integration
   surface) — not on every `STANDARD` feature.

<!-- aitk-model-route:create-feature.review -->
3. After verification (step 6) reaches `PASS`, dispatch a fresh reviewer
   through `skills/review/references/sol-review.md`'s procedure in full —
   Dispatch, Validate findings before fixing, Gate and record, Escalate only
   when triggered — with Scope: the resulting diff, Author identity:
   `implementation-worker` (never the worker that implemented the feature
   reviews its own work). Do not restate its dispatch or findings-translation
   steps here; its own Gate and record step already emits the
   `rules/gates.md` six-state block this workflow branches on, and its own
   step 4 escalates to `delta-review.md` when triggered — no separate
   escalation step is needed here.

4. Only proceed to step 7 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here
— for a `COMPLEX`/low-confidence `SINGLE_PHASE` unit, or for any `BATCHED`
unit regardless of complexity tier. Emit the Phase Plan block per
`rules/complexity-gate.md`'s Complex Path section immediately after the Size
Gate, before step 1 below. Its `Phases:` list names this workflow's own
execution units — implementation slices for a `SINGLE_PHASE` unit, or
waves/items for a `BATCHED` one — never architecture-decomposition phases;
those belong only to `MULTI_PHASE`'s Multi-Phase Path below, via
`decompose-work.md`.

<!-- aitk-model-route:create-feature.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the feature request as Goal. It returns a plan
   decomposed into the smallest implementable slices, each with
   entrance/exit criteria and a scope boundary, per
   `skills/implement-change/SKILL.md`'s Slice Awareness section. Never
   implement from an unreviewed plan the planner itself approved — the
   planner only proposes.

2. For each slice or wave/item, in order: dispatch the Standard Path's
   implement and optional test-authoring steps (steps 1–2) against that
   unit's scope; then verify it using `skills/verification-loop/SKILL.md`
   against gate name `create-feature-verify`, scoped to that unit — follow
   its RETRY/ESCALATE handling exactly, same as step 6 above; once that
   verification reaches `PASS`, dispatch the Standard Path's review step
   (step 3). This reuses the `create-feature.implement` /
   `create-feature.test-authoring` / `create-feature.review` boundaries
   above per unit — it is a loop over the same dispatch sites, not new ones.
   Move to the next unit only once this one's review Gate block reaches
   `PASS`. For a `BATCHED` shape specifically, also run one final aggregate
   verification against gate name `create-feature-verify` after the last
   wave/item, before step 7 — per-wave verification alone does not confirm
   the waves compose correctly together.

3. Every slice or wave/item verifies and reviews within its own iteration of
   step 2 — step 6 above does not run again once the Complex Path is
   running. Only proceed to step 7 (completion) once every unit's review
   Gate block reaches `PASS` (and, for `BATCHED`, the final aggregate
   verification also reaches `PASS`).

## Multi-Phase Path

Runs in place of every other path when step 2's Size Gate derives
`execution_shape: MULTI_PHASE`. Complexity (step 1) does not select a path
for the unit as a whole here — `decompose-work.md` reclassifies each phase
independently, and that phase's own classification picks its path.

**This path does not use `bin/aitk checkpoint advance()`.** That mechanism
resumes only through a fixed, pre-declared phase list keyed to a named
workflow contract in `interfaces/contracts.json` (e.g. its own legacy
`create-feature` contract there hardcodes `plan`/`implement`/`verify`/
`review`) — it has no way to accept the phase names `decompose-work.md`
derives at runtime for this specific feature. Cross-phase persistence here
is hand-set `PROJECT.md` frontmatter (same convention as the Size Gate
fields above) plus `aitk gate-state set` under a gate name scoped per phase
— never the checkpoint contract system, which stays reserved for the fixed
utility/legacy workflows that already declare their phases up front.

`decompose-work.md` and `plan-phase.md` each carry their own
`aitk-model-route` marker; this path calls them as procedures, so it
registers no new dispatch boundary of its own.

1. Run `skills/planning/references/decompose-work.md` once for the whole
   unit. Its `architecture_plan_status` must reach `PASS` before continuing
   — on `RECLASSIFY`/`ESCALATE`, stop and surface it rather than guessing a
   phase list. Persist its architecture artifact (boundaries, dependencies,
   global invariants, phase exit goals) as its own section in the durable
   plan artifact for this unit (`PLAN.md`, or a `PROJECT.md` body section if
   no `PLAN.md` was opened) — never inside the frontmatter fields below,
   which hold only the current phase's own classification.

2. For each phase, in the decomposition's declared order:
   a. Hand-set `current_phase` to that phase's name on `PROJECT.md`'s
      frontmatter — a short slug, matching the source plan's own example
      (`current_phase: layout-editing`).
   b. Reclassify complexity and size for this phase alone
      (`phase_complexity`, `phase_size`, `phase_execution_shape`, and — if
      needed — a fresh `phaseability_reason`) using steps 1–2 above, scoped
      to this phase's work only. A phase that itself classifies
      `MULTI_PHASE` recurses into this same path one level down rather than
      being forced flat.
   c. Run `skills/planning/references/plan-phase.md` for this phase; its
      `phase_plan_status` must reach `PASS` before implementation starts.
      `plan-phase.md`'s own planning retry budget
      (`reasoning_attempts.phase_plan`) is independent from the gate-state
      repeat-failure count in step (e) below — do not conflate the two, and
      do not reset one when the other resets.
   d. Implement and verify this phase using whichever path its own
      `phase_execution_shape` selects from step (b) — steps 3–7 above for
      `SINGLE_PHASE`, the Complex Path's per-slice/wave loop for `BATCHED`,
      or a nested Multi-Phase Path for a rare nested `MULTI_PHASE` phase —
      reusing the same `create-feature.implement` /
      `create-feature.test-authoring` / `create-feature.review` boundaries;
      no new dispatch boundaries per phase.
   e. Verify the phase against gate name
      `create-feature-phase-<phase name>-verify` (substituting this phase's
      `current_phase` slug) via `skills/verification-loop/SKILL.md`, so
      `aitk.gates.decide_failure`'s repeat-failure counting stays scoped to
      this phase and does not bleed into the next one's history. Record the
      decided state via `aitk gate-state set` before moving on — this is the
      phase checkpoint: a fresh context resuming mid-unit reads
      `current_phase` plus this phase-scoped gate history to know exactly
      which phase is in flight and what it has already tried, with no need
      to replay the whole unit.
   f. On `PASS`, move to the next phase. On `RECLASSIFY`/`ESCALATE` from
      either the phase plan or its verification, stop and surface it — do
      not silently reorder or drop a phase from the decomposition.

3. Once every phase's gate reaches `PASS`, proceed to step 7 (completion),
   recording the full phase history (every phase's gate outcome), not just
   the last phase's frontmatter fields.

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Certainty: Clear / Uncertain
Reason: [one line]
```
followed by the Size Gate block, the Phase Plan block (`COMPLEX` or
`BATCHED` only), the `verification-loop` Gate block(s) (every path — one per
phase for `MULTI_PHASE`), the review Gate block (`STANDARD`, `COMPLEX`, and
each `MULTI_PHASE` phase), then a short summary of the feature once every
gate reaches `PASS`.

## Notes

- This skill is now the live dispatch target for natural-language "create
  feature" / "build" / "implement" requests — Claude Code's own skill
  selection prefers this narrower description over the general
  `skills/workflows` router, same as `fix-bug`. The
  `interfaces/workflows.json` `create-feature` entry now points its
  `reference` directly at this file; `aitk/checkpoint.py`'s `_contract()`
  never read reference content (only `load_workflows` and
  `interfaces/contracts.json`), so nothing required the old duplicate — the
  standalone `skills/workflows/references/create-feature.md` has been
  deleted.
- Enforcing never-self-verify specifically for planner output (the Complex
  and Multi-Phase Paths' own plan step) is a later commit's extension to
  `aitk.gates`'s tests, not this one's.
