# Universal Principles

## Golden Rules
- **PROJECT.md is current context; PLAN.md is the active plan** — PROJECT.md holds lightweight state (what we're working on, where we are, durable decisions). PLAN.md holds the formal plan when standard-path planning produced one. Both are local-only and must never be committed to git.
- **No PII on public surfaces** — never put customer names, ticket IDs (Shortcut `sc-XXXXX` / Linear / Jira), customer-identifying URLs, or other PII in anything destined for a public repo: PR titles, bodies, comments, and commit messages. Describe the bug or behaviour generically ("embedded dashboard with tabs", not "Customer X's dashboard"). Keep IDs and reporter context in local-only files (PROJECT.md, commit notes). Chat summaries back to the user and local files are fine — the constraint is about content that lands on GitHub or another public destination.
- **Default engineering discipline** — evidence over assumptions, a working solution before optimization, small verified increments, TDD, YAGNI, and documented reasoning for decisions future maintainers will need.
- **Canonical workflows own their internal loops** — planning, review, and
  validation phases continue automatically until a threshold or blocker; do not
  surface internal phases as the next user step unless explicitly requested
- **Use durable state only for project workflows** — long-running or mutating workflows that need resume context must update PROJECT.md before finishing or crossing a checkpoint. Read-only answers, reviews, diagnostics, and utility commands must not create or modify workflow state unless the user explicitly requests a report artifact. The formal plan lives in PLAN.md when substantial planning produced one; it persists until the user explicitly cleans it up via `archive-project-file`.
- **Write through symlinks via the resolved real path** — some provider file tools refuse to write through symlinks. When PROJECT.md, PLAN.md, or any toolkit-managed file is a symlink, resolve it (`readlink -f <path>`) and edit the real path. Reads work through symlinks unchanged.
- **Checkpoint when context is deep** — see `rules/context-management.md` for thresholds and protocol
- **Rules evolve from usage** — see `rules/rule-maintenance.md` for how to strengthen, update, or extract rules

## Agent Context Model
- **Rules are always-on constraints and routing hints** — keep them short; point to skills or deeper docs instead of carrying task libraries.
- **Skills own workflow context** — natural-language routing and explicit skill invocation select canonical procedures; provider adapters only translate capabilities.
- **Skill descriptions are classifiers** — make trigger and non-trigger boundaries explicit. Put skill-only rules, lessons, and gotchas beside the skill.

## Communication Rules
Be direct about errors with no unnecessary apologies; show actual commands/output/evidence rather than just claims; explain the reasoning behind a non-obvious choice; ask rather than assume when direction is genuinely unclear; get confirmation before destructive changes.

## Override Hierarchy

1. **Universal principles** (this file) — always apply
2. **Orchestration rules** — multi-tool workflows
3. **Domain-specific rules** — testing, investigation, etc.
4. **Project-specific provider guidance** — repository context such as AGENTS.md or CLAUDE.md
5. **PROJECT.md current state** — most immediate context
