---
name: fix-bug
description: Use when the user reports a bug, broken behavior, or asks to fix or diagnose something, and the fix classifies TRIVIAL under rules/complexity-gate.md (single mechanical fix, 8/10+ confidence). Do NOT use for STANDARD or COMPLEX bugs (multi-file, unclear root cause, cross-system, or below 8/10 confidence) — this skill only covers the trivial fast-path today; emit RECLASSIFY and hand off to skills/workflows/references/fix-bug.md for those.
---

# Fix Bug (Trivial)

## Before Starting

Read `rules/complexity-gate.md` and `rules/gates.md` first — they define the
classification block, the trivial fast-path rules, and the six-state gate
contract this skill applies. This skill is the v2 goal-skill entry point for
bug fixes; it currently implements only the TRIVIAL branch. STANDARD and
COMPLEX are not yet built here — `skills/workflows/references/fix-bug.md` is
still the live workflow for those and remains on the pre-rename
TRIVIAL/MODERATE/STANDARD vocabulary until its own goal-skill branches land.

## Scope

**In scope:** classify the bug report, and when it is TRIVIAL, implement the
fix inline, verify it, and record completion.

**Out of scope:** anything that is not TRIVIAL. Do not attempt STANDARD or
COMPLEX bugs here — reclassify and hand off instead of forcing a multi-file or
ambiguous-root-cause fix through the trivial path.

## Steps

1. Emit the Complexity Gate block per `rules/complexity-gate.md`:
   ```markdown
   ## Complexity Gate
   Classification: TRIVIAL / STANDARD / COMPLEX
   Confidence: X/10
   Reason: [one line]
   ```
2. If the classification is not `TRIVIAL`, or confidence is below `8/10`:
   emit a Gate block with `State: RECLASSIFY`, persist it, and stop — hand the
   bug off to `skills/workflows/references/fix-bug.md` instead of continuing
   here:
   ```
   aitk gate-state set --file PROJECT.md --gate fix-bug-classify --state RECLASSIFY --reason "<why not trivial>" --count 0
   ```
3. If `TRIVIAL` at `8/10` confidence or higher: implement the fix inline, per
   the Trivial Fast-Path rules in `rules/complexity-gate.md` — no subagent
   spawns for the implementation itself, no formal planning phase.
4. Verify the fix using `skills/verification-loop/SKILL.md` against gate name
   `fix-bug-verify`. Follow its RETRY/ESCALATE handling exactly — one fix
   attempt on `RETRY`, stop and surface to the user on `ESCALATE`.
5. On `PASS`: record a completion entry on `PROJECT.md` and summarize the fix
   for the user. A `PASS` gate is a checkpoint, not license to stop before
   this step — see `rules/gates.md`'s Continuation Rule.

## Output

```markdown
## Complexity Gate
Classification: TRIVIAL
Confidence: X/10
Reason: [one line]
```
followed by the `verification-loop` Gate block, then a short summary of the
fix once verification `PASS`es.

## Notes

- This skill is dual-run alongside `skills/workflows/references/fix-bug.md`
  today; nothing dispatches "fix bug" requests here yet (that wiring is a
  later commit). Reading and testing it does not change live behavior.
- STANDARD and COMPLEX branches, and the dual-run router pointer that makes
  this skill a live dispatch target, land in later commits.
