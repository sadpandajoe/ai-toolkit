# Severity Definitions

Two tag systems coexist in the toolkit. Both are valid — use the one native to your domain. The mapping below lets cross-domain consumers translate.

## Code Review Severity

Action tags for iterative review/fix loops (`review-code`, `review-pr`, `review/references/code-quality.md`):

| Tag | Meaning | When to use |
|-----|---------|-------------|
| `[major]` | Must fix before proceeding | Logic errors, missing tests for changed behavior, security issues, data integrity risks |
| `[minor]` | Should fix | Naming, DRY violations, incomplete docs, missing edge-case handling |
| `[nitpick]` | Optional | Style preferences, micro-optimizations, cosmetic issues |

## Plan Review Severity

Impact labels for plan and design review findings (`plan-review/references/architecture.md`, `plan-review/references/implementation.md`, etc.):

| Tag | Meaning | When to use |
|-----|---------|-------------|
| `[High]` | Blocks implementation or introduces significant risk | Architectural flaws, missing requirements, security gaps |
| `[Medium]` | Notable gap that should be addressed but does not block | Incomplete coverage, suboptimal approach, missing edge cases |
| `[Low]` | Minor observation or suggestion | Style preferences, alternative approaches, nice-to-haves |

## QA Bug Severity

For bug reports filed by the `qa` skill (`references/file-bug.md`):

| Severity | Indicators |
|----------|-----------|
| **high** | Data loss, security bypass, crash, blocks core user workflow, affects many users |
| **medium** | Incorrect behavior with workaround available, non-blocking regression, affects some users |
| **low** | Cosmetic misalignment, rare edge case, minor impact with no workaround needed |

## Cross-Domain Mapping

| Code Review | Plan Review | QA Bug | Meaning |
|-------------|-------------|--------|---------|
| `[major]` | `[High]` | high | Must address before proceeding |
| `[minor]` | `[Medium]` | medium | Should address |
| `[nitpick]` | `[Low]` | low | Optional |
