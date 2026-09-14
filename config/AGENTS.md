# AI Toolkit

AI Toolkit is installed at `{{TOOLKIT_DIR}}`.

- Before acting, read and follow `{{TOOLKIT_DIR}}/rules/universal.md`,
  `{{TOOLKIT_DIR}}/rules/resource-management.md`, and
  `{{TOOLKIT_DIR}}/rules/context-management.md`. These are the canonical
  always-on rules declared by `interfaces/guidance.json`.
- Describe the outcome in plain language; the `$workflows` skill selects the
  workflow, classifies complexity and size, persists the routing snapshot in
  `PROJECT.md`, and drives the gates. Specialists (planner, RCA, independent
  reviewer) run only where their reasoning is worth the cost.
- Treat `skills/` as canonical behavior. Provider adapters translate syntax and
  tool names but preserve safety, authorization, state, verification, and
  reporting semantics.
- Keep read-only answers read-only. For mutating or long-running workflows, use
  the durable state the selected workflow declares.
- Before publishing or destructive actions, obey the workflow's authorization
  boundary and verification gate.
- Resolve shared capability identifiers through
  `{{TOOLKIT_DIR}}/config/providers/codex.md` before delegating, planning,
  creating worktrees, scheduling, or requesting independent review.
