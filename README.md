# AI Toolkit

A provider-portable toolkit for repeatable AI-assisted software delivery. You
describe the outcome in plain language; the toolkit selects the workflow,
classifies the work, persists routing state, and drives goal-seeking gates on
Claude Code and Codex CLI.

## Mental Model

- **Rules** are short, always-on constraints: durable state, gates, model roles.
- **Skills** are the canonical provider-neutral workflows and domain procedures.
- **Agents** are a small roster of fresh-context workers (`agents/claude/`,
  `agents/codex/`) plus provider-neutral specialist contracts
  (`agents/specialists/`) for independent review, RCA, and plan validation.
- **Interfaces** declare the stable public workflow names, contracts, routes,
  and dispatch boundaries.
- **`aitk`** builds guidance, validates every manifest, owns the `PROJECT.md`
  routing snapshot and checkpoint, and turns structural drift into
  deterministic failures.

## How a Request Runs

```
You: "Fix this bug" / "Add X" / "Review this branch and fix anything important"
  → the workflows skill matches the goal workflow
  → the parent (Sonnet or Sol) inspects, classifies, and persists the snapshot:
      Complexity TRIVIAL | STANDARD | COMPLEX   Size S | M | L | XL   Shape SINGLE_PHASE | BATCHED | MULTI_PHASE
  → the goal loop runs bounded capabilities, each returning a compact handoff
  → every gate answers PASS | RETRY | ESCALATE | RECLASSIFY | USER_DECISION | BLOCKED
    (one retry per owner, a bounded escalation ladder, STRONG verification before any push)
  → specialists (Opus planner, Sol reviewer or RCA) enter only where classification says so
  → PROJECT.md checkpoints each phase; fresh workers are the context boundary
```

You intervene only for a real product or design choice, a fact only you hold, a
blocked environment, or a publish, destructive, or production authorization.

## Model and Effort Routing

| Role | Claude | Codex | Effort | When |
|---|---|---|---|---|
| Orchestrator (parent session) | Sonnet | Sol | high | Always: classification, goal loop, TRIVIAL and STANDARD work |
| `implementation` | Sonnet | Sol | high | Substantial edits and tests from an accepted artifact |
| `planning` | Opus | Sol | high | COMPLEX decomposition or a COMPLEX phase plan, read-only |
| `review` | Opus | Sol | high | The one independent code, plan, or PR review, preferring the other provider |
| `deep-review` | Fable | Sol | xhigh | Adversarial, architecture, or security lens on flagged risk |
| `rca` | Opus | Sol | high | Independent RCA validation when the parent's hypothesis is uncertain |
| `deep-rca` | Fable | Sol | xhigh | Competing, intermittent, or cross-system causes after `rca` stayed uncertain |
| `operations` | Sonnet | Sol | high | Read-only evidence reduction and deterministic reports |

Exact selectors live only in `interfaces/model-routing.json`; promoting a model
changes one catalog entry. Routes never fall back to a weaker model, never
select `max` automatically, and a rejected request is unavailable rather than
downgraded. See `rules/model-assignment.md`.

Suggested parent-session settings for Claude Code: `/model sonnet` (the
orchestrator policy; `opusplan` would put Opus in the parent for every plan),
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2`, and a lower
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` if the parent grows quickly. No workflow ever
requires a manual clear.

## Quick Start

```bash
git clone https://github.com/sadpandajoe/ai-toolkit.git ~/opt/code/ai-toolkit
cd ~/opt/code/ai-toolkit
./setup.sh          # claude, codex, tmux, node
./install.sh        # build and link adapters, skills, and agents without replacing personal config
bin/aitk check
bin/aitk doctor --installed --strict
```

## What Gets Installed

| File | Purpose |
|------|---------|
| `~/.claude/CLAUDE.md` | Personal instructions with an idempotent toolkit-managed guidance block |
| `${CODEX_HOME:-~/.codex}/AGENTS.md` | Codex personal instructions with the same managed block |
| `~/.claude/skills/<skill>` | Per-skill Claude links for public skills |
| `~/.agents/skills/<skill>` | Cross-provider Agent Skill links used by Codex |
| `~/.claude/agents/aitk-*.md` | Native Claude agents: planner (Opus), implementer, debugger, tester (Sonnet), reviewer fallback (Opus) |
| `${CODEX_HOME:-~/.codex}/agents/aitk-*.toml` | Native Codex agents with pinned effort and sandbox |
| `~/.ai-toolkit/install-state.json` | Mode-0600 ownership ledger and one-level rollback record |

Only skills classified `public_router` or `public_direct` in
`interfaces/skills.json` are linked. Internal skills stay packaged for resolver
use. The repository root is also a validated Codex plugin
(`.codex-plugin/plugin.json`); the optional PGM extension remains
source-linked-only (`interfaces/support.json`).

The Codex agent TOML files pin `model_reasoning_effort` and `sandbox_mode` and
inherit the parent's model; verify the key set against your Codex CLI's
custom-agent documentation after upgrades.

## Repository Structure

```
ai-toolkit/
├── bin/aitk                # Build, doctor, routing, checkpoint, project-state CLI
├── aitk/                   # Standard-library implementation
├── agents/
│   ├── claude/             # Native Claude subagents (aitk-planner, aitk-implementer, aitk-debugger, aitk-tester, aitk-reviewer)
│   ├── codex/              # Native Codex custom agents (TOML)
│   └── specialists/        # Provider-neutral contracts: reviewer.md, rca.md, plan-validator.md
├── interfaces/
│   ├── workflows.json      # Stable core workflow manifest
│   ├── contracts.json      # Safety, state, resume, and verification contracts
│   ├── skills.json         # Public/internal skill classification
│   ├── providers.json      # Provider capability bindings
│   ├── model-routing.json  # Selectors, routes, dispatch boundaries, lens floors
│   ├── guidance.json       # Always-on rule inventory
│   └── support.json        # Supported release matrix
├── config/                 # CLAUDE.md / AGENTS.md templates and provider bindings
├── rules/
│   ├── universal.md        # Core principles (always on)
│   ├── resource-management.md  # Capacity and agent-tree limits (always on)
│   ├── context-management.md   # Workers as phase boundaries; no manual clear (always on)
│   ├── gates.md            # PASS / RETRY / ESCALATE / RECLASSIFY / USER_DECISION / BLOCKED and the retry budget
│   ├── specialist-handoff.md   # Maximum handoff into and out of a worker
│   ├── complexity-gate.md  # Complexity, size, and execution shape
│   ├── orchestration.md    # Goal loop, isolation mechanisms, batch rules
│   ├── model-assignment.md # Roles and routes
│   ├── durable-workflows.md    # Snapshot, checkpoint, and effect protocol
│   ├── code-review.md      # One independent review, validate before fix, delta review
│   ├── implementation.md   # Worker scope and test-first modes
│   ├── testing.md          # Evidence before completion
│   ├── severity.md         # Finding severity vocabularies
│   ├── ci-evidence.md      # CI signals are summaries; open the artifact
│   ├── rule-maintenance.md # Observation-driven rule changes
│   ├── input-detection.md  # Ticket, issue, and PR reference detection
│   ├── shortcut-api.md     # Shortcut REST routing hint
│   └── preset-environments.md  # Preset staging and VPN reachability
├── skills/                 # Canonical Agent Skills (see skills/README.md)
│   ├── workflows/          # Public router + goal workflow references
│   ├── verification-loop/  # Shared verify, fix, recheck loop
│   ├── planning/           # Sized planning, decomposition, phase plans, validation
│   ├── review/             # Independent review, deep lenses, PR review and posting
│   ├── debug/              # Investigation, RCA gate, CI diagnosis
│   ├── testing/ qa/ pm/ plan-review/ feedback/ pr-watch/ reflection/
│   ├── implement-change/   # Bounded implementation worker contract
│   ├── workstreams/        # Fan-in after parallel slices
│   ├── reporting/ metrics-emit/ archive-project-file/
│   ├── preflight/ cherry-pick/ agent-setup-maintainer/
│   └── shortcut/ superset-local/ preset-rbac-setup/   # Domain integrations
├── evals/                  # Judgment and deterministic eval cases
├── hooks/                  # Provider-neutral safety hooks + Codex hook adapter
├── extensions/pgm/         # Optional program-management extension
└── tests/                  # Deterministic guarantees
```

## Public Workflows

The `workflows` skill is the public interface; natural language selects the
workflow. Explicit requests use `$workflows <name>`; PGM requests use `$pgm
<name>` after opt-in installation.

| What you want | What you say | Workflow |
|---|---|---|
| Bug fix | "Fix this bug / ticket." | `fix-bug` |
| Feature | "Add X." | `create-feature` |
| Review and fix | "Review this branch and fix important issues." | `review-code` |
| Read-only review | "Review this; don't change anything." | `review-code` (review-only) |
| CI | "Fix the failing CI." | `fix-ci` |
| Feedback | "Address the review comments." | `address-feedback` |
| PR review | "Review PR 123." | `review-pr` |
| Watch | "Watch PR 123." | `watch-pr` |
| Backport | "Backport these commits to 6.0." | `$cherry-pick` |
| Plan check | "Validate this plan." | `review-plan` |

CLI:

| Command | Purpose |
|---|---|
| `bin/aitk list [--with-pgm] [--details]` | List workflows and contracts |
| `bin/aitk route "<request>"` | Deterministically suggest a workflow |
| `bin/aitk project-state init\|show\|set\|gate\|advance\|phases\|phase` | Read and update the `PROJECT.md` routing snapshot and gate budget |
| `bin/aitk checkpoint init\|validate\|advance\|reserve\|apply` | Durable phases and idempotent effects |
| `bin/aitk model-route <route> --provider <p> --boundary <id> [--lens <path>]` | Resolve a pinned specialist dispatch |
| `bin/aitk model-run <route> --provider <p> --boundary <id> --prompt-file <f>` | Run one fail-closed specialist |
| `bin/aitk build [--check] [--with-pgm]` | Generate path-resolved guidance |
| `bin/aitk doctor [--strict] [--installed]` | Structured health checks |
| `bin/aitk install [--with-pgm]` / `uninstall` / `rollback` | Transactional lifecycle |
| `bin/aitk check` | Build drift, doctor, tests, hook smoke tests |

See [Architecture](docs/ARCHITECTURE.md), [migration guidance](docs/MIGRATION.md),
[telemetry](docs/TELEMETRY.md), the [completion audit](docs/COMPLETION_AUDIT.md),
and the [changelog](CHANGELOG.md).

## Migrating from Slash Commands

AI Toolkit 0.2.0 removed its generated Claude slash aliases; 0.3.0 keeps the
natural-language interface and changes what runs underneath (see
[docs/MIGRATION.md](docs/MIGRATION.md)).

| Before 0.2.0 | Now |
|---|---|
| `/fix-bug <report>` | `Fix this bug: <report>` or `$workflows fix-bug <report>` |
| `/create-feature <request>` | `Build this feature: <request>` or `$workflows create-feature <request>` |
| `/review-code` | `Review my local changes` or `$workflows review-code` |
| `/review-plan` | `Validate this plan` or `$workflows review-plan` |
| `/fix-ci` | `Fix the failing CI checks` or `$workflows fix-ci` |
| Any other core `/name [args]` | `$workflows name [args]` or its natural-language trigger |
| `/create-status-report` | `$pgm create-status-report` after `--with-pgm` installation |

Claude's built-in `/review` remains available; `$workflows review-code` adds the
independent lane, validation, fixes, and the delta pass.

## Workflow Rules

The manifest owns direct workflow loading. Skill-owned and always-on loaders are
described without workflow names so the table cannot imply manifest wiring that
does not exist.

| File | Owner / direct workflow loaders |
|------|---------------------------------|
| `rules/universal.md` | Always-on provider guidance |
| `rules/resource-management.md` | Always-on provider guidance |
| `rules/context-management.md` | Always-on provider guidance |
| `rules/gates.md` | `address-feedback`, `create-feature`, `create-tests`, `fix-bug`, `fix-ci`, `review-code`, `review-code-adversarial`, `review-plan`, `review-pr`, `update-tests` |
| `rules/durable-workflows.md` | `address-feedback`, `create-feature`, `create-tests`, `fix-bug`, `fix-ci`, `review-code`, `review-code-adversarial`, `review-plan`, `review-pr`, `run-test-plan`, `test-pr`, `update-tests`, `watch-pr` |
| `rules/complexity-gate.md` | `address-feedback`, `create-feature`, `fix-bug`, `fix-ci`, `review-code`, `review-pr` |
| `rules/input-detection.md` | `create-feature`, `fix-bug`, `run-test-plan`, `test-pr` |
| `rules/preset-environments.md` | `run-test-plan`, `test-pr` |
| `rules/orchestration.md` | Workflows router and goal-loop policy |
| `rules/model-assignment.md` | Routed worker contract |
| `rules/specialist-handoff.md` | Routed worker contract and agent roster |
| `rules/code-review.md` | Review skill and reviewer contract loaders |
| `rules/implementation.md` | Implementation skill loader |
| `rules/testing.md` | Testing and implementation skill loaders |
| `rules/severity.md` | Review, planning, and QA skill loaders |
| `rules/ci-evidence.md` | Debug and watch skill loaders |
| `rules/shortcut-api.md` | Shortcut skill loader |
| `rules/rule-maintenance.md` | Reflection skill loader |

## Hooks (optional)

Hooks enforce toolkit rules at runtime. The shell guards are provider-neutral;
only their registration is provider-specific.

| Hook | Event | Behavior |
|------|-------|----------|
| `prevent-project-commit.sh` | PreToolUse (Bash) | Blocks unsafe git flags, force-pushes to main/master, and commits of local workflow state files |
| `pre-push-validate.sh` | PreToolUse (Bash) | Runs repository-pinned lint and targeted tests before a push |
| `check-resources.sh` | PreToolUse (Bash) | Warns when running tests with constrained resources |
| `check-plan-drift.sh` | Stop | Warns at turn end when PLAN.md outpaces PROJECT.md |
| `agent-setup-edit-reminder.sh` | PostToolUse (Edit/Write/MultiEdit/NotebookEdit) | Reminds to load `agent-setup-maintainer` when an agent-setup file is edited |

```bash
./install-hooks.sh           # Install Claude hooks
./install-hooks.sh --remove  # Remove Claude hooks
```

Codex hooks ship in the plugin at `hooks/hooks.json`; trust them through
`/hooks` after enabling the plugin.

## Updating

```bash
cd ~/opt/code/ai-toolkit
git pull
./install.sh
bin/aitk doctor --installed --strict
```

## Customization

Edit files directly in this repo. Skills and agents take effect through source
links; provider guidance is regenerated by `bin/aitk build`, and `./install.sh`
refreshes the managed block idempotently.

- **Add a workflow**: add its reference under `skills/workflows/references/`,
  register it in `interfaces/workflows.json` and `interfaces/contracts.json`,
  then run `bin/aitk build`.
- **Add a worker**: add `agents/claude/aitk-<name>.md` and
  `agents/codex/aitk-<name>.toml`; re-run `./install.sh`.
- **Change a model**: edit the catalog entry in `interfaces/model-routing.json`.
- **Add an eval**: append a case to `evals/<family>/cases.jsonl`.

## Environment Variables

```bash
export GITHUB_TOKEN="your-github-token"
export OPENAI_API_KEY="your-openai-key"          # For Codex CLI
export CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2    # goal skill → worker → one exceptional child
```

## Uninstall and Rollback

```bash
bin/aitk uninstall
bin/aitk rollback
```

Uninstall removes only ledger-owned links and managed guidance blocks. Rollback
refuses drift or a corrupt backup and can be applied once.

## Extensions

| Extension | Purpose | Install |
|-----------|---------|---------|
| `extensions/pgm/` | Program management reports (status, velocity) | `./install.sh --with-pgm` |
