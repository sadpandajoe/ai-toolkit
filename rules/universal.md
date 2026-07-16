# Universal Principles

## Golden Rules
- **PROJECT.md is current context; PLAN.md is the active plan** — PROJECT.md holds lightweight state (what we're working on, where we are, durable decisions). PLAN.md holds the formal plan when standard-path planning produced one. Both are local-only and must never be committed to git.
- **No PII on public surfaces** — never put customer names, ticket IDs (Shortcut `sc-XXXXX` / Linear / Jira), customer-identifying URLs, or other PII in anything destined for a public repo: PR titles, bodies, comments, and commit messages. Describe the bug or behaviour generically ("embedded dashboard with tabs", not "Customer X's dashboard"). Keep IDs and reporter context in local-only files (PROJECT.md, commit notes). Chat summaries back to the user and local files are fine — the constraint is about content that lands on GitHub or another public destination.
- **Evidence over assumptions** — use version control history, test results, existing solutions
- **Working solution before optimization** — get it working, commit, then improve
- **Incremental progress** — small, verified changes over big risky ones
- **Document decisions and reasoning** — future maintainers need context
- **TDD and YAGNI** — test first, build only what's needed now
- **End-to-end commands own their internal loops** — planning, review, and validation sub-phases should continue automatically until threshold or blocker; do not surface subcommands as the next user step unless the user explicitly chose them
- **Update PROJECT.md before completing any workflow** — every command or ad-hoc work session that produces results must write current status, what was done, and remaining items to PROJECT.md before finishing. The formal plan lives in PLAN.md during the workflow; it persists in place after completion until the user explicitly cleans up via `/archive-project-file`. Workflows do not auto-delete files.
- **Write through symlinks via the resolved real path** — Claude Code's Write/Edit refuses to write through a symlink (`Refusing to write through symlink: ...`). When PROJECT.md, PLAN.md, or any toolkit-managed file is a symlink (common in `.claudette`/worktree-shared-state setups), first resolve it (`readlink -f <path>`), then Read and Write/Edit the resolved real path. Reads work through symlinks unchanged.
- **Checkpoint when context is deep** — see `rules/context-management.md` for thresholds and protocol
- **Rules evolve from usage** — see `rules/rule-maintenance.md` for how to strengthen, update, or extract rules

## Agent Context Model
- **Rules are always-on constraints and routing hints** — keep them short; point to commands, skills, or deeper docs instead of carrying task libraries.
- **Commands expand prompts** — they create context for a workflow and may reference skill paths, but skills are selected from descriptions and the expanded prompt.
- **Skill descriptions are classifiers** — make trigger and non-trigger boundaries explicit. Put skill-only rules, lessons, and gotchas beside the skill.

## Communication Rules
- **Be direct about errors** — no unnecessary apologies
- **Show, don't tell** — include actual commands, outputs, evidence
- **Explain reasoning** — why one approach over another
- **Ask for clarification** — don't assume when unclear
- **Request confirmation** — before destructive changes

## Override Hierarchy

1. **Universal principles** (this file) — always apply
2. **Orchestration rules** — multi-tool workflows
3. **Domain-specific rules** — testing, investigation, etc.
4. **Project-specific CLAUDE.md** — project context
5. **PROJECT.md current state** — most immediate context
