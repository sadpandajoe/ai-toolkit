---
name: agent-setup-maintainer
description: Review, audit, update, or refactor this AI toolkit's own setup — its skills, agents, rules, hooks, plugin manifests, and scripts — for Claude Code and Codex. Use when adding or changing a skill, agent, rule, or hook here, or when asked whether toolkit content is still needed. Do NOT use for product code, app features, bug fixes, or product QA.
---

# Agent Setup Maintainer

The toolkit is facts and boundaries, not procedure. Hold every change to the
admission rule in `AGENTS.md`: a line exists only if it is a fact the model
can't infer, a boundary a hook or script enforces, a format surviving code
parses, or a Claude Code ↔ Codex portability shim. Procedure, generic advice,
checklists and state machines go out of date with each model release, so
delete them rather than reword them. When a newer model regresses on a task,
add the missing fact or boundary; never put the procedure back.

## Layout

- `rules/universal.md`: the only always-on text, injected by
  `hooks/session-start.sh`. Boundaries only; keep it under about 300 words.
- `skills/<name>/SKILL.md`: one skill per outcome, triggered by its
  description alone. Frontmatter is exactly `name` and `description`. Start
  from [the template](../../docs/templates/SKILL.md). A script a skill runs
  lives in `skills/<name>/scripts/`.
- `agents/claude/<name>.md` and `agents/codex/<name>.toml`: an agent earns its
  place only by context isolation (noisy logs, browser runs), independence
  (review), or a different tool or model set. The Claude body and the Codex
  `developer_instructions` must be identical; a test holds them equal.
- `hooks/`: deterministic boundaries. `hooks/lib/git_guard.py` is standalone
  (standard library plus `shell_tokens`); a rule the hook enforces needs no
  prose beyond one line in `rules/universal.md`.
- `.claude-plugin/` and `.codex-plugin/`: the install. Codex plugins can't
  ship agents, so `install.sh` links `agents/codex/*.toml`.

## Before handing off

Read [lessons.md](lessons.md) before changing how a skill briefs a worker.
Run `python3 scripts/check.py`, `python3 -m unittest discover -s tests`, and
`git diff --check`.
