# Severity

Finding severity is separate from workflow gate status (`rules/gates.md`):
severity grades one finding; the gate grades the round.

## Code Review

| Tag | Meaning | Use for |
|---|---|---|
| `[major]` | Must fix before proceeding | Logic errors, missing tests for changed behavior (calibrated by the missing-test table in `rules/code-review.md`), security, data integrity |
| `[minor]` | Should fix | Naming, duplication, incomplete docs, missing edge cases |
| `[nitpick]` | Optional | Style, micro-optimizations, cosmetics |

## Plan, RCA, and Brief Review

| Tag | Meaning |
|---|---|
| `[High]` | Blocks implementation or invalidates the approach |
| `[Medium]` | Notable gap; address, does not block |
| `[Low]` | Observation or alternative |

Plan-domain lanes return a verdict line: `Verdict: APPROVE | CHANGES_REQUIRED |
REPLAN`.

## QA Bugs

QA bug severity (high, medium, low) and its mapping to these tags live in
`skills/qa/references/file-bug.md`.
