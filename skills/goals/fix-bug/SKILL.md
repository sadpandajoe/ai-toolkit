---
name: fix-bug
description: Use when the user reports a bug, broken behavior, or asks to fix or diagnose something. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md, and the full S/M/L/XL size axis under aitk/size_axis.py. Do NOT use for feature work, refactors, or requests that aren't a bug fix — see skills/goals/create-feature or the relevant domain skill instead.
---

# Fix Bug

## Effect Boundary

Effect: `git_mutation`.

## Durable Runtime Contract

Follow the [durable workflow runtime](../../../rules/durable-workflows.md). The
phase graph, authorization gates, and effect keys are the `fix-bug` entry in
`interfaces/contracts.json`; use `bin/aitk checkpoint` for every durable
transition and effect record.

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
investigate with `debug-worker`, gate the RCA, implement and optionally
test with native specialists, then review. Registers dispatch boundaries
`fix-bug.investigate` / `fix-bug.implement` / `fix-bug.test-authoring` /
`fix-bug.review`.

→ Full procedure: [references/standard-path.md](references/standard-path.md)

## Complex Path

Runs in place of the Trivial and Standard branches when step 3 routes here —
for a `COMPLEX`/low-confidence `SINGLE_PHASE` bug, or for any `BATCHED`
shape regardless of complexity tier. Plans via a dedicated `planner`, then
runs the Standard Path per slice or wave/item. Registers dispatch boundary
`fix-bug.plan`.

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
`BATCHED` only), the RCA Gate block (`STANDARD`, and any `COMPLEX`/
`MULTI_PHASE` unit that runs the Standard Path), the `verification-loop`
Gate block(s) (every path — one per phase for `MULTI_PHASE`), the review
Gate block (every path except plain `TRIVIAL`), then a short summary of the
fix once every gate reaches `PASS`.

## Notes

- This skill is now the live dispatch target for natural-language "fix bug" /
  "diagnose" / "broken behavior" requests — Claude Code's own skill selection
  prefers this narrower description over the general `skills/workflows`
  router. The `interfaces/workflows.json` `fix-bug` entry now points its
  `reference` directly at this file; `aitk/checkpoint.py`'s `_contract()`
  never reads reference content (only `load_workflows` and
  `interfaces/contracts.json`), so nothing required the old duplicate — the
  standalone `skills/workflows/references/fix-bug.md` (pre-rename
  TRIVIAL/MODERATE/STANDARD vocabulary) has been deleted.
