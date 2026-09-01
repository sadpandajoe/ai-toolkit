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
`fix-bug`, there is no root-cause investigation phase — survey existing
patterns inline, implement with a native specialist, then review. Registers
dispatch boundaries `create-feature.implement` /
`create-feature.test-authoring` / `create-feature.review`.

→ Full procedure: [references/standard-path.md](references/standard-path.md)

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here —
for a `COMPLEX`/low-confidence `SINGLE_PHASE` unit, or for any `BATCHED`
unit regardless of complexity tier. Plans via a dedicated `planner`, then
runs the Standard Path per slice or wave/item. Registers dispatch boundary
`create-feature.plan`.

→ Full procedure: [references/complex-path.md](references/complex-path.md)

## Multi-Phase Path

Runs in place of every other path when step 2's Size Gate derives
`execution_shape: MULTI_PHASE`. Runs `decompose-work.md` once, then
`plan-phase.md` and implementation/verification per phase, tracked via
hand-set `PROJECT.md` frontmatter and phase-scoped `aitk gate-state` — not
`bin/aitk checkpoint advance()`, which only resumes a fixed pre-declared
phase list. This is the canonical Multi-Phase Path other goal skills mirror.

→ Full procedure: [references/multi-phase-path.md](references/multi-phase-path.md)

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
