---
name: fix-ci
description: Use when a CI build or check has failed and you want to diagnose and fix it. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md. Do NOT use for bug fixes unrelated to CI (skills/goals/fix-bug), feature work (skills/goals/create-feature), or refactors — this skill only fixes failing CI runs.
---

# Fix CI

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, and
`rules/specialist-handoff.md` first — they define the classification block,
the fast-path rules, the six-state gate contract, and the input/output shape
for every specialist dispatch this skill uses. This skill is the v2
goal-skill entry point for CI failures, implementing all three complexity
tiers.

## Scope

**In scope:** normalize the CI input, gather real failing log output,
classify the failure; for TRIVIAL, apply the safe fix inline; for STANDARD,
investigate then implement via native specialists, with one fresh reviewer
before completion; for COMPLEX, plan first via a dedicated planner, then run
the Standard Path per slice — one slice per independent root cause when a
run has more than one; verify and record completion on every path.

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
   Confidence: X/10
   Reason: [one line]
   ```
5. If the classification is `COMPLEX`, or confidence is below `8/10` at any
   tier: follow the Complex Path below instead of applying step 3's
   classification inline or using the Standard Path.
6. If `TRIVIAL` at `8/10` confidence or higher: apply the fix produced by
   step 3's classification inline, per the Trivial Fast-Path rules in
   `rules/complexity-gate.md` — no subagent spawns for the fix itself, no
   formal planning phase. Skip to step 8.
7. If `STANDARD` at `8/10` confidence or higher, follow the Standard Path
   below instead of applying step 3's classification inline.
8. For `TRIVIAL` and `STANDARD` only: verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-ci-verify`,
   running the closest local equivalent of the failing CI step as `command`
   — see `skills/debug/references/ci-verify-fix.md`'s STRONG standard for
   what "closest equivalent" means. Follow the loop's RETRY/ESCALATE
   handling exactly — one fix attempt on `RETRY`, stop and surface to the
   user on `ESCALATE`. `COMPLEX` skips this step — the Complex Path verifies
   per slice and goes straight to step 9.
9. On `PASS`: record a completion entry on `PROJECT.md` and summarize the fix
   for the user. A `PASS` gate is a checkpoint, not license to stop before
   this step — see `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 7 and 8 above, in place of applying step 3's
classification inline:

<!-- aitk-model-route:fix-ci.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to deepen the root-cause analysis beyond step 3's
   classification — reproduce the failure locally when possible, confirm the
   root cause, and check whether other failures in the group share it. If its
   Evidence summary shows the root cause is still ambiguous, cross-system, or
   the fix needs an architectural decision, emit `State: RECLASSIFY` toward
   `COMPLEX` (step 5 above) instead of continuing — do not push an unclear
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
4. After verification (step 8) reaches `PASS`, dispatch one fresh reviewer via
   the `review` route (`rules/model-assignment.md`) against the resulting
   diff — never the worker that implemented the fix; never review your own
   work. Translate its findings into a `rules/gates.md` Gate block using the
   Mapping From the Old Mechanisms section: clean or micro-fix-only findings
   → `PASS`; a fixable finding → `RETRY`; the same finding recurring after a
   fix attempt → `ESCALATE`; an unresolved required finding with no ambiguity
   → `BLOCKED`; a genuine trade-off → `USER_DECISION`.

5. Only proceed to step 9 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 5 routes here —
either because a single failure is genuinely ambiguous or architectural, or
because step 3 grouped the run into more than one independent root cause.
Emit the Phase Plan block per `rules/complexity-gate.md`'s Complex Path
section immediately after the Complexity Gate, before step 1 below. Its
`Phases:` list names this workflow's own phases (plan → per-slice
implementation loop → completion) — never the planner's slices, which don't
exist until step 1 returns.

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

2. For each slice, in order: dispatch the Standard Path's investigate,
   implement, and optional test-authoring steps (steps 1–3) against that
   slice's scope; then verify the slice's fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-ci-verify`,
   scoped to that slice — follow its RETRY/ESCALATE handling exactly, same
   as step 8 above; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 4). This reuses the `fix-ci.investigate`
   / `fix-ci.implement` / `fix-ci.test-authoring` / `fix-ci.review`
   boundaries above per slice — it is a loop over the same dispatch sites,
   not new ones. Move to the next slice only once this slice's review Gate
   block reaches `PASS`.

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-ci.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) and check the
   result against `skills/debug/references/review-rca.md`'s RCA Gate
   Evidence Checklist before treating it as ready for implementation.

4. Every slice verifies and reviews within its own iteration of step 2 — step
   8 above does not run again for `COMPLEX`. Only proceed to step 9
   (completion) once every slice's review Gate block reaches `PASS`.

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD / COMPLEX
Confidence: X/10
Reason: [one line]
```
followed by the Phase Plan block (COMPLEX only), the `verification-loop`
Gate block (every path), the review Gate block (STANDARD and COMPLEX), then
a short summary of the fix once every gate reaches `PASS`.

## Notes

- This skill is now the live dispatch target for natural-language "fix CI" /
  "CI failure" requests — Claude Code's own skill selection prefers this
  narrower description over the general `skills/workflows` router, same as
  `fix-bug`. The old `skills/workflows/references/fix-ci.md` and its
  `interfaces/workflows.json` entry stay in place — durable-contract
  infrastructure, not dispatch (see `fix-bug`'s Notes for why); they stay on
  the pre-rename trivial/moderate/standard vocabulary indefinitely.
