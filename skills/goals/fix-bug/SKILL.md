---
name: fix-bug
description: Use when the user reports a bug, broken behavior, or asks to fix or diagnose something, and the fix classifies TRIVIAL or STANDARD under rules/complexity-gate.md at 8/10+ confidence. Do NOT use for COMPLEX bugs (unclear or cross-system root cause, architectural trade-offs, or below 8/10 confidence at any tier) — this skill does not yet cover the complex path; emit RECLASSIFY and hand off to skills/workflows/references/fix-bug.md for those.
---

# Fix Bug

## Before Starting

Read `rules/complexity-gate.md`, `rules/gates.md`, and
`rules/specialist-handoff.md` first — they define the classification block,
the fast-path rules, the six-state gate contract, and the input/output shape
for every specialist dispatch this skill uses. This skill is the v2
goal-skill entry point for bug fixes; it currently implements the TRIVIAL and
STANDARD branches. COMPLEX is not yet built here —
`skills/workflows/references/fix-bug.md` is still the live workflow for it
and remains on the pre-rename TRIVIAL/MODERATE/STANDARD vocabulary until its
own goal-skill branch lands.

## Scope

**In scope:** classify the bug report; for TRIVIAL, implement the fix inline;
for STANDARD, investigate then implement via native specialists, with one
fresh reviewer before completion; verify and record completion on both paths.

**Out of scope:** COMPLEX bugs. Do not force an unclear-root-cause or
cross-system fix through either path here — reclassify and hand off instead.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Confidence: X/10
   Reason: [one line]
   ```
2. If the classification is `COMPLEX`, or confidence is below `8/10` at any
   tier: emit a Gate block with `State: RECLASSIFY`, persist it, and stop —
   hand the bug off to `skills/workflows/references/fix-bug.md` instead of
   continuing here:
   ```
   aitk gate-state set --file PROJECT.md --gate fix-bug-classify --state RECLASSIFY --reason "<why not trivial/standard>" --count 0
   ```
3. If `TRIVIAL` at `8/10` confidence or higher: implement the fix inline, per
   the Trivial Fast-Path rules in `rules/complexity-gate.md` — no subagent
   spawns for the implementation itself, no formal planning phase. Skip to
   step 5.
4. If `STANDARD` at `8/10` confidence or higher, follow the Standard Path
   below instead of implementing inline.
5. Verify the fix using `skills/verification-loop/SKILL.md` against gate name
   `fix-bug-verify`. Follow its RETRY/ESCALATE handling exactly — one fix
   attempt on `RETRY`, stop and surface to the user on `ESCALATE`.
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

- This skill is dual-run alongside `skills/workflows/references/fix-bug.md`
  today; nothing dispatches "fix bug" requests here yet (that wiring is a
  later commit). Reading and testing it does not change live behavior.
- The COMPLEX branch, and the dual-run router pointer that makes this skill a
  live dispatch target, land in later commits.
