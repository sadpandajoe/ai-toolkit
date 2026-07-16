# AI Toolkit

AI Toolkit is installed at `{{TOOLKIT_DIR}}`.

- Before acting, read and follow `{{TOOLKIT_DIR}}/rules/universal.md`,
  `{{TOOLKIT_DIR}}/rules/resource-management.md`, and
  `{{TOOLKIT_DIR}}/rules/context-management.md`. These are the canonical
  always-on rules declared by `interfaces/guidance.json`.
- Use the `$workflows` skill for end-to-end feature, bug, CI, testing, QA, review, PR, checkpoint, and maintenance work.
- Treat `skills/` as canonical behavior. Provider adapters may translate syntax and tool names but must preserve safety, authorization, state, verification, and reporting semantics.
- Keep read-only answers read-only. For mutating or long-running workflows, use the durable state file required by the selected workflow.
- Before publishing or destructive actions, obey the workflow's explicit authorization boundary and verification gate.
- Resolve shared capability identifiers through `{{TOOLKIT_DIR}}/config/providers/codex.md`; read that binding before planning boundaries, delegation, worktrees, context resets, recurrence, or independent review.
