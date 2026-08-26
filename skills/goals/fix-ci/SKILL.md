---
name: fix-ci
description: Use when a CI build or check has failed and you want to diagnose and fix it, and the failure classifies TRIVIAL under rules/complexity-gate.md (single mechanical fix, 8/10+ confidence). Do NOT use for STANDARD or COMPLEX CI failures (novel, cross-cutting, behavioral, or below 8/10 confidence) — this skill only covers the trivial fast-path today; emit RECLASSIFY and hand off to skills/workflows/references/fix-ci.md for those.
---

# Fix CI (Trivial)

## Before Starting

Read `rules/complexity-gate.md` and `rules/gates.md` first — they define the
classification block, the trivial fast-path rules, and the six-state gate
contract this skill applies. This skill is the v2 goal-skill entry point for
CI failures; it currently implements only the TRIVIAL branch. STANDARD and
COMPLEX are not yet built here — `skills/workflows/references/fix-ci.md` is
still the live workflow for those and remains on the pre-rename
trivial/moderate/standard vocabulary until its own goal-skill branches land.

## Scope

**In scope:** normalize the CI input, gather real failing log output,
classify the failure, and when it is TRIVIAL, apply the safe fix inline,
verify it locally, and record completion.

**Out of scope:** anything that is not TRIVIAL. Do not attempt STANDARD or
COMPLEX CI failures here — reclassify and hand off instead of forcing a
novel, cross-cutting, or behavioral fix through the trivial path.

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
5. If the classification is not `TRIVIAL`, or confidence is below `8/10`:
   emit a Gate block with `State: RECLASSIFY`, persist it, and stop — hand the
   failure off to `skills/workflows/references/fix-ci.md` instead of
   continuing here:
   ```
   aitk gate-state set --file PROJECT.md --gate fix-ci-classify --state RECLASSIFY --reason "<why not trivial>" --count 0
   ```
6. If `TRIVIAL` at `8/10` confidence or higher: apply the fix produced by
   step 3's classification inline, per the Trivial Fast-Path rules in
   `rules/complexity-gate.md` — no subagent spawns for the fix itself, no
   formal planning phase.
7. Verify the fix using `skills/verification-loop/SKILL.md` against gate name
   `fix-ci-verify`, running the closest local equivalent of the failing CI
   step as `command` — see `skills/debug/references/ci-verify-fix.md`'s
   STRONG standard for what "closest equivalent" means. Follow the loop's
   RETRY/ESCALATE handling exactly — one fix attempt on `RETRY`, stop and
   surface to the user on `ESCALATE`.
8. On `PASS`: record a completion entry on `PROJECT.md` and summarize the fix
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

- This skill is dual-run alongside `skills/workflows/references/fix-ci.md`
  today; nothing dispatches "fix CI" requests here yet (that wiring is a
  later commit). Reading and testing it does not change live behavior.
- STANDARD and COMPLEX branches, and the dual-run router pointer that makes
  this skill a live dispatch target, land in later commits.
