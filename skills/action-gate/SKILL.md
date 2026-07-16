---
name: action-gate
description: Use when a workflow needs an execution gate after investigation, classification, or cold-read planning. Do NOT use before evidence gathering or as a substitute for the workflow's domain decision.
---

# Action Gate

Use this helper after an investigation or classification phase has produced a root-cause hypothesis, a proposed fix, and a validation plan.

## Output Contract

Always end with this block:

```markdown
## Execution Gate

Risk: LOW / MED / HIGH
Confidence: X/10
Decision Required: YES / NO
Verification Strength: STRONG / PARTIAL / WEAK

Recommendation:
- Proceed automatically
- Ask for approval
- Stop and escalate
```

## Auto-Proceed Rule

Proceed without asking the user only when all of the following are true:

- `Risk: LOW`
- `Confidence: 8/10` or higher
- `Decision Required: NO`
- `Verification Strength` is not `WEAK`, **or** it is `WEAK` but a downstream verifier will exercise the change (e.g., CI on the PR for `fix-ci` and `watch-pr` flows — "cannot reproduce locally, CI is the verifier" is routine). Note `WEAK + downstream-verified` in the gate block. With WEAK verification and no downstream verifier, stop — and the no-push-after-failed-verification invariant always holds regardless.

`--gate-strict` removes the WEAK carve-out (unconditional WEAK stop) for callers that want the most conservative behavior.

Otherwise stop and surface the reason clearly.

## Verification Strength

Default tier definitions (when `debug/references/ci-verify-fix.md` is in play, use its expanded definitions instead):

- **STRONG**: ran the failing command (or close equivalent) locally and it passes.
  Example: "Ran `pytest tests/unit/test_dashboard.py` — the same test CI reported failing — and it passes after the fix."
- **PARTIAL**: ran related checks that exercise the changed code, not the exact failing command.
  Example: "Ran `mypy superset/models/dashboard.py` (type-check on the changed file), but the CI failure was in an integration test that requires Docker."
- **WEAK**: code review only, no local execution.
  Example: "Reviewed the diff and confirmed the logic change matches the root cause, but no local execution was possible — the test requires a running app with seed data."

## Rating Guidance

Set `Decision Required: YES` when:

- multiple root causes or fix interpretations are plausible
- the fix changes product or runtime behavior in a meaningful way
- the workflow would widen scope beyond the failing surface
- branch, environment, or validation assumptions are ambiguous

Set `Risk: LOW` only when the fix is narrow, behavior-preserving, and locally verifiable with routine checks.

Treat confidence numerically:

- `8-10` = high confidence
- `5-7` = medium confidence
- `1-4` = low confidence

## Decision Required: YES Example

"The CI failure could be caused by either (a) a stale TypeScript declaration or (b) a genuine type incompatibility from the PR. Option (a) is a 1-line rebuild fix; option (b) requires changing the function signature. Set `Decision Required: YES` because the fix approach differs materially."

## Confidence Calibration

- **9-10**: Root cause confirmed by local reproduction. Fix is narrow and behavior-preserving.
- **7-8**: Root cause strongly supported by evidence but not directly reproduced. Fix is targeted.
- **5-6**: Root cause plausible but alternative explanations exist. Fix scope may need adjustment.
- **3-4**: Multiple plausible root causes. Investigation incomplete.
- **1-2**: Root cause unknown. Evidence is indirect or contradictory.
