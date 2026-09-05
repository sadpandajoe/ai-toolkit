# Severity

Finding severity is separate from workflow gate status (`rules/gates.md`):
severity grades one finding; the gate grades the round.

## Code Review

| Tag | Meaning | Use for |
|---|---|---|
| `[major]` | Must fix before proceeding | Logic errors, missing tests for changed behavior, security, data integrity |
| `[minor]` | Should fix | Naming, duplication, incomplete docs, missing edge cases |
| `[nitpick]` | Optional | Style, micro-optimizations, cosmetics |

## Plan, RCA, and Brief Review

| Tag | Meaning |
|---|---|
| `[High]` | Blocks implementation or invalidates the approach |
| `[Medium]` | Notable gap; address, does not block |
| `[Low]` | Observation or alternative |

Plan-domain lanes return a verdict line (`Verdict: APPROVE | CHANGES_REQUIRED |
REPLAN`) instead of a numeric score.

## QA Bug

| Severity | Indicators |
|---|---|
| high | Data loss, security bypass, crash, blocks a core workflow, affects many users |
| medium | Incorrect behavior with a workaround, non-blocking regression |
| low | Cosmetic, rare edge case, minor impact |

## Cross-Domain Mapping

`[major]` = `[High]` = high (must address); `[minor]` = `[Medium]` = medium
(should address); `[nitpick]` = `[Low]` = low (optional).
