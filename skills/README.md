# Skills

Skills are domain-scoped Agent Skills selected when their description matches the task. Each skill lives in its own folder under `skills/` and follows the same anatomy.

## Folder Anatomy

```
skills/<name>/
├── SKILL.md                  required — frontmatter + routing
├── agents/openai.yaml        optional — Codex UI and invocation policy
├── rules.md                  optional — scoped rules loaded with the skill
├── gotchas.md                optional — known traps with incident references
├── lessons.md                optional — patterns learned the hard way
├── references/*.md           optional — per-phase steps, output templates, reviewer prompts
├── templates/*.md            optional — fill-in shapes (summary blocks, checkpoints)
├── examples/*.md             optional — concrete worked examples
├── scripts/*.sh              optional — bundled helpers invokable from the skill
└── assets/*                  optional — images, fixtures, anything binary
```

**SKILL.md frontmatter fields:**

| Field | Meaning |
|-------|---------|
| `name` | Skill name. Must match folder name. |
| `description` | The classifier. Lead with **trigger phrases** users say; end with explicit **Do NOT use** boundaries. |

Shared frontmatter intentionally contains only these two portable fields. Put Codex display metadata and `policy.allow_implicit_invocation` in `agents/openai.yaml`; keep concrete provider model/tool configuration in provider adapters.

**The "Before Starting" line** at the top of every SKILL.md:
```
Read any sibling `rules.md`, `lessons.md`, and `gotchas.md` files if present.
```
This convention ensures scoped guidance loads without bloating always-on context.

## When each file fires

- `rules.md` — always read when the skill is invoked. Same shape as global `/rules` files.
- `gotchas.md` — "don't do X, here's what bit us." Concrete failure modes with incident references.
- `lessons.md` — "do Y, here's what worked." Patterns the user has validated.
- `references/*.md` — phase-specific steps the orchestrator reads inline or passes to a subagent. The umbrella `SKILL.md` routes to them by intent.
- `templates/*.md` — output shapes a workflow fills in (summary blocks, checkpoints).

## Umbrella Index

End-to-end workflow umbrellas:

| Umbrella | Use for |
|----------|---------|
| [workflows/](workflows/) | Public daily-workflow routing and canonical orchestration references |
| [debug/](debug/) | Investigating bugs, diagnosing failures, RCA review, CI failure classification, fix verification |
| [feedback/](feedback/) | PR review feedback triage, approved fixes, reviewer replies, and thread handling |
| [pr-watch/](pr-watch/) | Watch-and-fix loop over an open PR — CI status + review comments, dispatching to debug/ and feedback/ |
| [reflection/](reflection/) | Memory capture, memory review/prune, failure postmortems, rule promotion |
| [planning/](planning/) | Producing/iterating technical plans, finalize cold read, classifying review findings as plan vs code |
| [pm/](pm/) | Product scoping before planning — feature briefs, acceptance criteria, milestones |
| [plan-review/](plan-review/) | Reviewer lenses that critique a plan: architecture, backend, frontend, feasibility |
| [qa/](qa/) | Triage, fix validation, impact assessment, use-case discovery, scenario expansion, bug filing |
| [testing/](testing/) | HOW to test — creating/updating automated test suites, reviewing test code |
| [review/](review/) | Reviewing code diffs — dispatching code-review lenses, code-quality, adversarial |
| [implement-change/](implement-change/) | Executing one approved slice of a plan |
| [cherry-pick/](cherry-pick/) | Cross-branch movement of isolated changes — safety gates, scope-leak detection |
| [preflight/](preflight/) | Worktree prep, dependency/env checks, Docker readiness before work begins |

Workflow scaffolding (mostly orchestrator-only; not auto-routed):

| Umbrella | Use for |
|----------|---------|
| [action-gate/](action-gate/) | Execution Gate block (Risk/Confidence/Decision/Verification) after investigation |
| [reporting/](reporting/) | Final summary + continuation checkpoint shapes |
| [metrics-emit/](metrics-emit/) | Append structured event to `.ai-toolkit/metrics.jsonl` |
| [workstreams/](workstreams/) | Fan-in after parallel implementation subagents finish |
| [archive-project-file/](archive-project-file/) | Move completed PROJECT.md content to PROJECT_ARCHIVE.md |
| [agent-setup-maintainer/](agent-setup-maintainer/) | Auditing or updating toolkit skills, rules, interfaces, and generated adapters |

Domain integrations:

| Umbrella | Use for |
|----------|---------|
| [shortcut/](shortcut/) | Shortcut REST API: fetch story, post report, attach artifacts |
| [superset-local/](superset-local/) | Superset-specific local Docker stack and Playwright glue |
| [preset-rbac-setup/](preset-rbac-setup/) | Seed canonical RBAC test users on a fresh Preset staging workspace |

## Designing a new skill

1. **Description first.** Write the trigger phrases and "Do NOT use" boundaries before any content. This is how the model decides whether to invoke.
2. **Pick the right level.** A new umbrella is justified only when 3+ references would share rules/gotchas. Otherwise add a reference to an existing umbrella.
3. **Keep SKILL.md as a routing table.** Steps and templates live in `references/`, not in SKILL.md itself. SKILL.md should fit on a screen.
4. **Co-locate guidance.** New gotchas go in this skill's `gotchas.md`, not in global `rules/`. Global rules are routing hints, not task libraries.
5. **Run `bin/aitk check`** after structural changes to catch broken cross-references, adapter drift, contract failures, and hook regressions.
