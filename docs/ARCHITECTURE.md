# Architecture

The toolkit is facts and boundaries. It has no workflow engine. Up to v0.3,
a Python runtime classified work by complexity, size and shape, ran
PASS/RETRY/ESCALATE gates with retry budgets, planned review lanes, and bound
prose paragraphs to a model-routing manifest. That machinery made up for
models that needed rails. Current models plan, verify and escalate on their
own, and every such rule went out of date with the next release. v0.4 keeps
only what doesn't decay.

## The admission rule

A line, file or module exists only if it is one of these:

1. **A fact the model can't infer.** Preset and Superset hosts and
   credentials, the external CI that `gh run list` doesn't show, cherry-pick
   incidents, browser-recording traps, the user's thresholds and preferences.
2. **A boundary a hook or script enforces.** The git guard, the production
   refusals in the Preset scripts.
3. **A format surviving code parses.** For example, the host table that
   `scripts/preset/hosts.mjs` and its test hold in step.
4. **A Claude Code ↔ Codex portability shim.**

A regression on a newer model is fixed by adding a fact or a boundary, never
by putting procedure back.

## Layers

| Layer | Where | Loaded |
|---|---|---|
| Rules | `rules/universal.md` | Every session, by `hooks/session-start.sh` |
| Skills | `skills/*/SKILL.md`, `extensions/pgm/skills/pgm/` | When a description matches the request |
| Agents | `agents/claude/*.md`, `agents/codex/*.toml` | When a skill hands work to a fresh context |
| Hooks | `hooks/hooks.json`, `hooks/*.sh`, `hooks/lib/` | On every Bash tool call and session start |
| Scripts | `skills/*/scripts/`, `scripts/` | When a skill runs them |

## Agents: when a fresh context pays

A subagent is justified only by context isolation, independence, or a
different tool or model set. Being "a simple task" isn't enough, because the
parent does simple work inline.

- `reviewer`: independence. It hasn't seen how the change was made. It is
  also the contract `second-opinion.py` sends to the other model family.
- `ci-investigator`: isolation. CI logs stay out of the parent's context.
- `qa-runner`: isolation. Browser runs and their artifacts stay out too.

Each agent is one body in two files. A Codex plugin can't ship agents, so
`install.sh` links the TOML files. `tests/test_plugin.py` holds the two
bodies equal.

## Cross-family review

`skills/review/scripts/second-opinion.py` runs `codex exec` from Claude Code
and `claude -p` from anywhere else. The run is read-only: Codex gets
`--sandbox read-only`; Claude gets plan mode, no write tools, and git
read-only commands only. The reviewer contract goes in as system or developer
instructions, and the diff (or a file such as `PLAN.md`) on stdin, so the
worker needs no file pointers.

## Local notes

`PROJECT.md`, `PROJECT_ARCHIVE.md`, `PLAN.md`, `WATCH.md`, `CHERRY_PICK.md`
and `CI_FIX.md` are freeform working notes with no schema. The git guard
refuses to commit them, and anything under `.ai-toolkit/`. The `handoff`
skill describes how to keep them.

## Install

Both CLIs install the repository root as a plugin from the one-plugin
marketplace in `.claude-plugin/marketplace.json`. Claude Code discovers
`skills/` and `hooks/hooks.json` by convention, and its manifest adds the PGM
skill and the agents. The Codex manifest names the skills and hooks. Codex
runs plugin hooks only after the user trusts them in `/hooks`.
