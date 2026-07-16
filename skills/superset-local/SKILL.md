---
name: superset-local
description: "Use for Superset local stack startup, frontend detection, explicit proxy fixes, and Playwright E2E. Do NOT use for production environments, generic Docker work, or unrelated web applications."
---

# Superset Local

## Before Starting

Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.

This is a project-specific environment skill for Superset/Preset local testing.

| Phase | When | Reference |
|-------|------|-----------|
| Start stack | Need a healthy local Superset stack and frontend URL | [references/start-stack.md](references/start-stack.md) |
| Run Playwright | Need to run Superset Playwright E2E tests against the local stack | [references/run-playwright.md](references/run-playwright.md) |

## Boundaries

- Use `preflight/` for generic dependency, env, and worktree readiness.
- Use `qa/` for scenario design and user-visible validation.
- Use this skill only for Superset-specific stack and Playwright mechanics.
