---
name: fix-ci
description: Use when a CI build or check has failed and you want to diagnose and fix it, and the failure classifies TRIVIAL or STANDARD under rules/complexity-gate.md at 8/10+ confidence. Do NOT use for COMPLEX CI failures (unclear or cross-system root cause, architectural trade-offs, or below 8/10 confidence at any tier) — this skill does not yet cover the complex path; emit RECLASSIFY and hand off to skills/workflows/references/fix-ci.md for those.
---

# Fix CI

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, and
`rules/specialist-handoff.md` first — they define the classification block,
the fast-path rules, the six-state gate contract, and the input/output shape
for every specialist dispatch this skill uses. This skill is the v2
goal-skill entry point for CI failures; it currently implements the TRIVIAL
and STANDARD branches. COMPLEX is not yet built here —
`skills/workflows/references/fix-ci.md` is still the live workflow for it and
remains on the pre-rename trivial/moderate/standard vocabulary until its own
goal-skill branch lands.

## Scope

**In scope:** normalize the CI input, gather real failing log output,
classify the failure; for TRIVIAL, apply the safe fix inline; for STANDARD,
investigate then implement via native specialists, with one fresh reviewer
before completion; verify and record completion on both paths.

**Out of scope:** COMPLEX CI failures. Do not force an unclear-root-cause,
cross-system, or architectural fix through either path here — reclassify and
hand off instead.

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
   verification cycle.
4. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Confidence: X/10
   Reason: [one line]
   ```
5. If the classification is `COMPLEX`, or confidence is below `8/10` at any
   tier: emit a Gate block with `State: RECLASSIFY`, persist it, and stop —
   hand the failure off to `skills/workflows/references/fix-ci.md` instead of
   continuing here:
   ```
   aitk gate-state set --file PROJECT.md --gate fix-ci-classify --state RECLASSIFY --reason "<why not trivial/standard>" --count 0
   ```
6. If `TRIVIAL` at `8/10` confidence or higher: apply the fix produced by
   step 3's classification inline, per the Trivial Fast-Path rules in
   `rules/complexity-gate.md` — no subagent spawns for the fix itself, no
   formal planning phase. Skip to step 8.
7. If `STANDARD` at `8/10` confidence or higher, follow the Standard Path
   below instead of applying step 3's classification inline.
8. Verify the fix using `skills/verification-loop/SKILL.md` against gate name
   `fix-ci-verify`, running the closest local equivalent of the failing CI
   step as `command` — see `skills/debug/references/ci-verify-fix.md`'s
   STRONG standard for what "closest equivalent" means. Follow the loop's
   RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`, stop and
   surface to the user on `ESCALATE`.
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

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL / STANDARD
Confidence: X/10
Reason: [one line]
```
followed by the `verification-loop` Gate block (both paths), the review Gate
block (STANDARD only), then a short summary of the fix once every gate
reaches `PASS`.

## Notes

- This skill is dual-run alongside `skills/workflows/references/fix-ci.md`
  today; nothing dispatches "fix CI" requests here yet (that wiring is a
  later commit). Reading and testing it does not change live behavior.
- The COMPLEX branch, and the dual-run router pointer that makes this skill a
  live dispatch target, land in later commits.
