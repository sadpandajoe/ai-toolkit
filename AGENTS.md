# AI Toolkit Development

- Admission rule: a line, file or module exists only if it is (1) a fact the
  model can't infer (org and repo facts, incident-derived gotchas, the user's
  thresholds and preferences, exact commands and APIs), (2) a boundary a hook
  or script enforces, (3) a format surviving code parses, or (4) a Claude
  Code ↔ Codex portability shim. Procedure, generic advice, checklists and
  state machines don't qualify. A regression on a newer model is fixed by
  adding a fact or a boundary, never by restoring procedure.
- Editing `skills/`, `rules/`, `agents/` or `hooks/`: load
  `agent-setup-maintainer` first.
- `SKILL.md` frontmatter contains only `name` and `description`; the
  description is the skill's only trigger.
- Keep user configuration non-destructive and idempotent. Preserve unrelated
  files, guidance, skills, commands, and hooks.
- Before handing off a toolkit change, run `python3 scripts/check.py`,
  `python3 -m unittest discover -s tests`, and `git diff --check`.
