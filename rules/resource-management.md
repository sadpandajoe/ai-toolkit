# Resource Management Principles

## Golden Rules
- [ ] **Check resources before consuming them** — Docker, test workers, builds
- [ ] **Fit work to measured capacity** — do not use container count as a proxy
- [ ] **Scale workers to available resources** — not to CPU count
- [ ] **Keep subagent spawn depth shallow** — a dispatched worker does its bounded task and returns; it does not itself dispatch further workers unless the calling procedure explicitly defines that second layer

## Routing

Use this file as the always-on index. Load the scoped rule only when the task needs it:

| Work | Read |
|------|------|
| Starting Docker or local app stacks | `skills/preflight/rules.md` |
| Entering or preparing a git worktree | `skills/preflight/rules.md` |
| Running Jest, pytest, Playwright, or similar suites | `skills/testing/rules.md` |

## Subagents as a Resource

A subagent spawn is a resource like Docker memory or test workers: bounded,
and worth checking before consuming. Two guardrails specific to subagents:

- **Whether to spawn at all** is `rules/orchestration.md`'s Inline-First
  Principle — this file does not restate that decision.
- **Spawn depth stays shallow, by default one level**: orchestrator dispatches
  a worker; that worker completes its bounded task and returns a compact
  result. A worker fanning out to further workers of its own multiplies cost
  and makes failures harder to trace — the orchestrator loses visibility into
  what the second layer did. Only go deeper when the calling procedure names
  that second layer explicitly (e.g. a decomposition step that hands off
  per-phase work to its own bounded dispatch) — never as an incidental choice
  a worker makes on its own.

## Always-On Guardrails

- Before starting containers, run `docker ps` and check **two things**:
  1. **Capacity fit** — read the daemon cap (`docker info | grep "Total Memory"`) and current aggregate use before starting a heavy stack. Estimate the new stack's footprint, show the math, and proceed if it fits. Ask only on genuine over-capacity, where starting the stack risks disrupting running work. `--ask` (or an explicit user preference) restores always-ask.
  2. **Which look stale** — surface any container running > 24h (column: `STATUS`) or whose name references an old branch/feature, list them with age, and ask the user whether to stop them. Do not stop without confirmation.
- Before heavy test runs, choose worker counts intentionally; do not blindly use CPU count.
- In worktrees, assume dependencies, build outputs, and env files may be missing until checked.

## Capacity Reference

Docker Desktop's memory cap is set independently of host RAM — check
`docker info | grep "Total Memory"` and `docker stats --no-stream` rather than
encoding one machine's hardware in a reusable rule. A Superset stack typically
uses 4–6 GB; use measured current consumption plus that estimate.

If the user is hitting capacity limits, suggest raising Docker Desktop → Settings → Resources → Memory rather than killing work. Do not change Docker Desktop settings programmatically.

Detailed stack, worktree, and worker-count rules are skill-scoped so they only load for environment prep or testing work.
