# Resource Management Principles

## Golden Rules
- **Check resources before consuming them** — Docker, test workers, builds
- **Fit work to measured capacity** — do not use container count as a proxy
- **Scale workers to available resources** — not to CPU count

## Routing

Use this file as the always-on index. Load the scoped rule only when the task needs it:

| Work | Read |
|------|------|
| Starting Docker or local app stacks | `skills/preflight/rules.md` |
| Entering or preparing a git worktree | `skills/preflight/rules.md` |
| Running Jest, pytest, Playwright, or similar suites | `skills/testing/rules.md` |

## Always-On Guardrails

Before starting containers, run `docker ps`; check capacity against the measured daemon cap (not container count) and flag any container idle >24h or tied to a stale branch before stopping it without confirmation — full procedure in `skills/preflight/rules.md`. Before heavy test runs, choose worker counts from measured resource pressure, not CPU count — full procedure in `skills/testing/rules.md`. In worktrees, assume dependencies, build outputs, and env files may be missing until checked.

If the user is hitting capacity limits, suggest raising Docker Desktop's memory cap rather than killing work; don't change Docker Desktop settings programmatically.
