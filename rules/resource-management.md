# Resource Management

## Golden Rules

- Check resources before consuming them: Docker, test workers, builds, agents.
- Fit work to measured capacity, not to container count or CPU count.
- Bound agent trees: one worker layer below the goal skill, one exceptional
  specialist child (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`). Parallel workers
  share the machine; two or three at once is the normal ceiling.

## Routing

| Work | Read |
|---|---|
| Starting Docker or local app stacks | `skills/preflight/rules.md` |
| Entering or preparing a git worktree | `skills/preflight/rules.md` |
| Running Jest, pytest, Playwright, or similar suites | `skills/testing/rules.md` |

## Always-On Guardrails

- Before starting containers, run `docker ps` and check two things: capacity
  fit (read the daemon cap with `docker info | grep "Total Memory"` and current
  aggregate use, estimate the new stack, show the math, proceed if it fits, ask
  only on genuine over-capacity) and staleness (list containers running over 24h
  or named for old branches, and ask before stopping any).
- Choose test worker counts intentionally.
- In worktrees, assume dependencies, build outputs, and env files may be missing.

## Capacity Reference

Docker Desktop's memory cap is independent of host RAM; measure it rather than
encoding one machine. A Superset stack typically uses 4 to 6 GB. If the user is
at capacity, suggest raising Docker Desktop memory rather than killing work, and
never change Docker settings programmatically.
