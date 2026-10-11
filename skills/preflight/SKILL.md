---
name: preflight
description: "Use for pre-work readiness checks and environment preparation before implementation or QA. Do NOT use to implement product changes or to replace workflow-specific verification."
---

# Preflight

Pre-work readiness checks. Preflight never starts Docker, dev servers, or
databases: it reports what the task needs. `superset-local` starts a Superset
stack when asked; for anything else, start only the services the repro needs
and record blockers.

- Entering a fresh git worktree: [references/worktree-preflight.md](references/worktree-preflight.md).
- Docker capacity, stale containers and the per-stack memory figure:
  `skills/workflows/references/check-resources.md`.
