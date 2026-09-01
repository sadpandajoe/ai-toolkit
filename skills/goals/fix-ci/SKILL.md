---
name: fix-ci
description: Use when a CI build or check has failed, a pipeline has gone red, or you want to diagnose and fix it. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md, and the full S/M/L/XL size axis under aitk/size_axis.py. Do NOT use for bug fixes unrelated to CI (skills/goals/fix-bug), feature work (skills/goals/create-feature), or refactors — this skill only fixes failing CI runs.
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
classification inline: investigate with `debug-worker`, implement and
optionally test with native specialists, then review. Registers dispatch
boundaries `fix-ci.investigate` / `fix-ci.implement` / `fix-ci.test-authoring`
/ `fix-ci.review`.

→ Full procedure: [references/standard-path.md](references/standard-path.md)

## Complex Path

Runs in place of the Trivial and Standard branches when step 6 routes here —
because a single failure is genuinely ambiguous or architectural, because
step 3 grouped the run into more than one independent root cause, or because
step 5's `execution_shape` is `BATCHED`. Plans via a dedicated `planner`,
then runs the Standard Path per slice or wave/item. Registers dispatch
boundary `fix-ci.plan`.

→ Full procedure: [references/complex-path.md](references/complex-path.md)

## Multi-Phase Path

Runs in place of every other path when step 5's Size Gate derives
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
