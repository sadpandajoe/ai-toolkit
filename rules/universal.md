# Universal Principles

## Golden Rules

- **Durable state is files, not chat.** `PROJECT.md` holds current state and the
  routing snapshot; `PLAN.md` holds the active plan when one was needed. Both are
  local-only and never committed. Resume from them, never from remembered chat.
- **No PII on public surfaces.** No customer names, ticket IDs (`sc-XXXXX`,
  Linear, Jira), customer URLs, or reporter identity in PR titles, bodies,
  comments, or commit messages. Describe behavior generically. Local files and
  chat summaries may carry the IDs.
- **Evidence before completion.** A gate passes on a command that ran and its
  result, never on inspection alone. Use history, tests, and existing fixes.
- **Resolve uncertainty yourself.** Investigate, read code, run checks. Ask the
  user only for a genuine product, design, or scope choice, a fact only they
  hold, or a protected effect. Those are the only `USER_DECISION` cases.
- **Regression evidence over ceremony.** Bug fixes get a test that fails before
  and passes after when feasible; features get acceptance tests as the spec.
  Test-first is a strong default, not a universal ritual; when blocked, write
  the test anyway and record the gap.
- **Working solution, then optimization.** Small verified steps, narrowest
  approach first, YAGNI.
- **Workflows own their loops.** Planning, verification, and review continue
  automatically through `RETRY` and `ESCALATE`; only `USER_DECISION`,
  `BLOCKED`, and hard safety gates surface to the user (`rules/gates.md`).
- **Read-only work stays read-only.** Answers, reviews, and diagnostics never
  create or modify workflow state unless the user asks for a report artifact.
- **Only the orchestrator writes state.** Workers return compact handoffs
  (`rules/specialist-handoff.md`); the parent updates `PROJECT.md` and `PLAN.md`.
- **Write through symlinks via the real path.** Resolve with `readlink -f` before
  editing toolkit-managed files.
- **Rules evolve from usage.** See `rules/rule-maintenance.md`.

## Agent Context Model

- Rules are short always-on constraints and routing hints.
- Skills own workflow context and load only at phase entry; descriptions are
  classifiers with explicit use and do-not-use boundaries.
- Provider adapters translate capabilities; they never own behavior.

## Communication

- Direct about errors, no apologies. Show commands and outputs.
- Explain the reasoning behind a choice in one line.
- Confirm before destructive or publishing actions; never before routine ones.

## Override Hierarchy

1. Universal principles (this file)
2. Gates and safety contracts (`rules/gates.md`, `interfaces/contracts.json`)
3. Orchestration and model rules
4. Domain rules (testing, implementation, review)
5. Repository guidance (`AGENTS.md`, `CLAUDE.md`)
6. `PROJECT.md` current state
