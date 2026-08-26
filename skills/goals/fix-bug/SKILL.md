---
name: fix-bug
description: Use when the user reports a bug, broken behavior, or asks to fix or diagnose something. Covers TRIVIAL, STANDARD, and COMPLEX under rules/complexity-gate.md. Do NOT use for feature work, refactors, or requests that aren't a bug fix — see skills/goals/create-feature or the relevant domain skill instead.
---

# Fix Bug

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, and
`rules/specialist-handoff.md` first — they define the classification block,
the fast-path rules, the six-state gate contract, and the input/output shape
for every specialist dispatch this skill uses. This skill is the v2
goal-skill entry point for bug fixes, implementing all three complexity
tiers.

## Scope

**In scope:** classify the bug report; for TRIVIAL, implement the fix inline;
for STANDARD, investigate then implement via native specialists, with one
fresh reviewer before completion; for COMPLEX, plan first via a dedicated
planner, then run the Standard Path per slice; verify and record completion
on every path.

**Out of scope:** feature work and refactors — this skill only fixes reported
bugs.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Confidence: X/10
   Reason: [one line]
   ```
2. If the classification is `COMPLEX`, or confidence is below `8/10` at any
   tier: follow the Complex Path below instead of implementing inline or
   using the Standard Path.
3. If `TRIVIAL` at `8/10` confidence or higher: implement the fix inline, per
   the Trivial Fast-Path rules in `rules/complexity-gate.md` — no subagent
   spawns for the implementation itself, no formal planning phase. Skip to
   step 5.
4. If `STANDARD` at `8/10` confidence or higher, follow the Standard Path
   below instead of implementing inline.
5. For `TRIVIAL` and `STANDARD` only: verify the fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-bug-verify`.
   Follow its RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`,
   stop and surface to the user on `ESCALATE`. `COMPLEX` skips this step —
   the Complex Path verifies per slice and goes straight to step 6.
6. On `PASS`: record a completion entry on `PROJECT.md` and summarize the fix
   for the user. A `PASS` gate is a checkpoint, not license to stop before
   this step — see `rules/gates.md`'s Continuation Rule.

## Standard Path

Runs between steps 4 and 5 above, in place of inline implementation:

<!-- aitk-model-route:fix-bug.investigate -->
1. Dispatch `debug-worker` per `rules/specialist-handoff.md` (Phase:
   investigate) to reproduce the bug and identify root cause. If its Evidence
   summary shows the root cause is still ambiguous, cross-system, or the fix
   needs an architectural decision, emit `State: RECLASSIFY` toward `COMPLEX`
   (step 2 above) instead of continuing — do not push an unclear cause
   forward into implementation.

<!-- aitk-model-route:fix-bug.implement -->
2. Dispatch `implementation-worker` (Phase: implement), handing it
   debug-worker's evidence pointer and a Scope naming the files the fix may
   touch. It writes the regression test first per `rules/implementation.md`'s
   Test-First Modes, then the minimal fix.

<!-- aitk-model-route:fix-bug.test-authoring -->
3. Dispatch `test-worker` separately only when investigation surfaced a
   test-coverage gap outside the fix's own regression test — not on every
   STANDARD fix.

<!-- aitk-model-route:fix-bug.review -->
4. After verification (step 5) reaches `PASS`, dispatch one fresh reviewer via
   the `review` route (`rules/model-assignment.md`) against the resulting
   diff — never the worker that implemented the fix; never review your own
   work. Translate its findings into a `rules/gates.md` Gate block using the
   Mapping From the Old Mechanisms section: clean or micro-fix-only findings
   → `PASS`; a fixable finding → `RETRY`; the same finding recurring after a
   fix attempt → `ESCALATE`; an unresolved required finding with no ambiguity
   → `BLOCKED`; a genuine trade-off → `USER_DECISION`.

5. Only proceed to step 6 (completion) once the review Gate block reaches
   `PASS`.

## Complex Path

Runs in place of the Trivial and Standard branches when step 2 routes here.
Emit the Phase Plan block per `rules/complexity-gate.md`'s Complex Path
section immediately after the Complexity Gate, before step 1 below. Its
`Phases:` list names this workflow's own phases (plan → per-slice
implementation loop → completion) — never the planner's slices, which don't
exist until step 1 returns.

<!-- aitk-model-route:fix-bug.plan -->
1. Dispatch the `planner` subagent per `rules/specialist-handoff.md` (Phase:
   plan), handing it the bug report as Goal. It returns a plan decomposed
   into the smallest implementable slices, each with entrance/exit criteria
   and a scope boundary, per `skills/implement-change/SKILL.md`'s Slice
   Awareness section. Never implement from an unreviewed plan the planner
   itself approved — the planner only proposes.

2. For each slice, in order: dispatch the Standard Path's investigate,
   implement, and optional test-authoring steps (steps 1–3) against that
   slice's scope; then verify the slice's fix using
   `skills/verification-loop/SKILL.md` against gate name `fix-bug-verify`,
   scoped to that slice — follow its RETRY/ESCALATE handling exactly, same
   as step 5 above; once that verification reaches `PASS`, dispatch the
   Standard Path's review step (step 4). This reuses the `fix-bug.investigate`
   / `fix-bug.implement` / `fix-bug.test-authoring` / `fix-bug.review`
   boundaries above per slice — it is a loop over the same dispatch sites,
   not new ones. Move to the next slice only once this slice's review Gate
   block reaches `PASS`.

3. If a slice's investigation surfaces an ambiguous, intermittent,
   historical, or cross-system root cause, escalate that slice's
   `fix-bug.investigate` dispatch from `rca` to `deep-rca` (the boundary
   declares both routes; see `rules/model-assignment.md`) and check the
   result against `skills/debug/references/review-rca.md`'s RCA Gate
   Evidence Checklist before treating it as ready for implementation.

4. Every slice verifies and reviews within its own iteration of step 2 — step
   5 above does not run again for `COMPLEX`. Only proceed to step 6
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

- This skill is now the live dispatch target for natural-language "fix bug" /
  "diagnose" / "broken behavior" requests — Claude Code's own skill selection
  prefers this narrower description over the general `skills/workflows`
  router. `skills/workflows/references/fix-bug.md` and its
  `interfaces/workflows.json` entry are retained only for literal
  `fix-bug`-command-name compatibility until Wave 8 deletes them; they stay on
  the pre-rename TRIVIAL/MODERATE/STANDARD vocabulary until then.
