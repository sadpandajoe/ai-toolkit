---
name: agent-setup-maintainer
description: Review, audit, update, or refactor AI coding-agent setup such as skills, adapters, rules, provider guidance, hooks, subagent prompts, or workflow orchestration. Use for Claude, Codex, and provider-portability maintenance. Do NOT use for product code, app features, bug fixes, or product QA.
---

# Agent Setup Maintainer Skill

## Before Starting

1. Read the relevant provider guidance templates under `config/` and the canonical interface manifest under `interfaces/`.
2. Inspect relevant source files under `skills/`, `rules/`, `interfaces/`, `hooks/`, and `config/`. Inspect `build/` or installed copies only when validating adapters or install output.
3. Before changing how a skill hands work to a worker, read [lessons.md](lessons.md).

## Core principles

- Rules are always-on constraints and routing hints — keep them short.
- Skills are selected via their descriptions; descriptions are classifiers, not documentation.
- Canonical behavior lives in skills; provider packages are thin adapters.
- Move task-specific detail into skills or referenced docs, not global rules.
- Prefer small surgical edits over broad rewrites.

## Checklist

- Does each skill have clear use cases and non-use cases?
- Are broad instructions moved out of global rules?
- Are routing hints present where skill selection needs reliability?
- Are sibling files linked from the phase that needs them?
- Are provider adapters exact, capability-preserving projections of canonical behavior?
- Are README, installer, and doctor checks updated when skill structure changes?

## Check

Run `bin/aitk check` after any change. It enforces markdown links, the
route-marker-to-boundary bijection, the `Effect:` and `Authorization mode:`
lines, and the contract graph.
