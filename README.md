# AI Toolkit

A provider-portable toolkit for repeatable AI-assisted software delivery. Canonical workflows live in Agent Skills and run through natural-language routing or explicit skill invocation.

## Mental Model

- **Rules** are short, always-on safety and routing constraints.
- **Skills** are the canonical provider-neutral workflows and domain procedures.
- **Interfaces** declare the stable public workflow names in `interfaces/workflows.json`.
- **Provider adapters** translate capabilities without duplicating workflow logic.
- **`aitk`** builds path-resolved guidance and turns structural drift into deterministic failures.
- **CI** runs the same `aitk check` gate on supported Python versions with SHA-pinned first-party actions.

## Model and Effort Routing

Keep the main coding session on a current Sol-or-newer or Opus workhorse at
high effort. Spawned workers use stable routes, so normal skills choose the
right family and effort without copying volatile model IDs into workflow text.

| Job | Route | Automatic effort | Codex | Claude |
|---|---|---|---|---|
| Implementation | `implementation` | high | Sol | Opus |
| Plan/code/test/PR review | `review` | high | Sol | Opus |
| Architecture, security, adversarial, final cold review | `deep-review` | xhigh | Sol | Fable |
| RCA | `rca` | high | Sol | Opus |
| Ambiguous or cross-system RCA | `deep-rca` | xhigh | Sol | Fable |
| Read-only evidence and deterministic operational summaries | `operations` | high | Sol | Sonnet |

Sonnet does not perform development judgment or effects: no implementation,
test execution/design, API/ticket mutation, diagnosis, RCA, or review. Fable is
a read-only deep advisor for reviews and RCA. Automatic routing never selects max and never falls back
to a weaker model or effort.

Exact current selectors live only in `interfaces/model-routing.json`. A future
Sol, Opus, Fable, or Sonnet promotion changes one catalog entry; route names,
skills, and this table remain stable. Resolve the installed toolkit/package
root, then use `<toolkit-root>/bin/aitk model-route` and
`<toolkit-root>/bin/aitk model-run --boundary <marker-id>`.

The runner proves the exact CLI request, absence of a fallback argument,
successful provider exit, and a valid structured result. Current provider
success formats do not attest the internal serving-model identity, so the
toolkit does not claim post-hoc verification of provider-side substitution.
Per-contract SHA-256 labels identify the inlined content for diagnostics; they
are not an independently anchored integrity check.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/sadpandajoe/ai-toolkit.git ~/opt/code/ai-toolkit
cd ~/opt/code/ai-toolkit

# 2. Install dependencies (claude, codex, tmux, node)
./setup.sh

# 3. Build and link provider adapters without replacing personal config
./install.sh

# 4. Verify both repository and installed state
bin/aitk check
bin/aitk doctor --installed --strict
```

## What Gets Installed

### Tools (via setup.sh)
| Tool | Purpose |
|------|---------|
| Node.js | Runtime for CLI tools |
| Claude Code | Anthropic's AI coding assistant |
| Codex CLI | OpenAI's AI coding tool |
| tmux | Terminal multiplexer |
| git | Version control |

### Configuration (via install.sh)
| File | Purpose |
|------|---------|
| `~/.claude/CLAUDE.md` | Personal instructions with an idempotent toolkit-managed guidance block |
| `${CODEX_HOME:-~/.codex}/AGENTS.md` | Codex personal instructions with the same non-destructive managed guidance model |
| `~/.claude/skills/<skill>` | Per-skill Claude links; unrelated skills are preserved |
| `~/.agents/skills/<skill>` | Canonical cross-provider Agent Skill links used by Codex |
| `~/.ai-toolkit/install-state.json` | Mode-0600 ownership ledger and one-level rollback record |

Only skills classified `public_router` or `public_direct` in
`interfaces/skills.json` are linked into discovery locations. Internal support
skills remain packaged for resolver-based use without becoming standalone
public entrypoints.

The repository root is also a validated Codex plugin package (`.codex-plugin/plugin.json`) with bundled core skills and lifecycle hooks. Use `install.sh` for source-linked local development; use the plugin form when publishing the core toolkit through a personal or team marketplace. The optional PGM extension is source-linked-only in version 0.2.0 because Codex plugin manifests expose one `skills/` tree; this boundary is explicit in `interfaces/support.json`. Codex supports both [Agent Skills locations](https://learn.chatgpt.com/docs/customization/skills) and [plugin distribution](https://learn.chatgpt.com/docs/build-plugins).

### Claude Adapter Capabilities
| Feature | Purpose |
|---------|---------|
| Task subagents | Explore, Plan, general-purpose for specialized work |
| Task tracking | TaskCreate/Update/List for progress visibility (optional) |
| Plan mode | EnterPlanMode/ExitPlanMode for structured planning |
| Native tools | Read, Grep, Glob instead of bash equivalents |

These names are isolated to the Claude adapter. Shared rules and skills use provider-neutral capability language.

## Repository Structure

```
ai-toolkit/
├── bin/aitk                # Deterministic build + doctor CLI
├── aitk/                   # Standard-library implementation
├── .codex-plugin/
│   └── plugin.json         # Codex plugin package manifest
├── interfaces/
│   ├── workflows.json      # Stable core workflow manifest
│   ├── contracts.json      # Safety, state, resume, and verification contracts
│   ├── skills.json         # Total public/internal skill classification
│   ├── providers.json      # Provider capability bindings
│   ├── model-routing.json  # Exact selectors, effort policy, and dispatch inventory
│   ├── guidance.json       # Shared always-on rule inventory
│   └── support.json        # Supported release matrix
├── setup.sh                # Install tools (run once)
├── install.sh              # Build and install provider adapters safely
├── PROJECT_TEMPLATE.md     # Template for project documentation
├── build/                  # Generated by install.sh (path-resolved copies)
│   └── config/             # Resolved provider guidance
├── config/
│   ├── CLAUDE.md           # Claude guidance adapter template
│   ├── AGENTS.md           # Codex guidance adapter template
│   └── providers/          # Capability bindings for Claude and Codex
├── rules/
│   ├── universal.md        # Core principles (loaded first)
│   ├── orchestration.md    # Multi-agent workflow rules
│   ├── model-assignment.md # Stable worker routes and family/effort policy
│   ├── context-management.md   # Context depth thresholds and checkpoint protocol
│   ├── durable-workflows.md    # Deterministic phase/effect checkpoint protocol
│   ├── rule-maintenance.md     # How to strengthen, update, or extract rules
│   ├── ci-evidence.md      # CI signals are summaries — open the artifact behind them
│   ├── implementation.md   # Code development
│   ├── testing.md          # Test strategy
│   ├── resource-management.md  # Worktrees, Docker, heavy tasks
│   ├── preset-environments.md  # Preset staging/prod envs, credentials, VPN reachability
│   ├── code-review.md      # Review guidelines
│   ├── complexity-gate.md  # Complexity classification and fast-path
│   ├── review-gate.md      # Review gate output contract
│   ├── scoring.md          # Review scoring scale
│   ├── severity.md         # Finding severity levels
│   ├── stop-rules.md       # Universal stop conditions for iterative loops
│   ├── shortcut-api.md     # Shortcut REST API routing hint
│   └── input-detection.md  # Route ticket/issue inputs to Shortcut or GitHub
├── skills/                  # Canonical Agent Skills; references load lazily (see skills/README.md for anatomy)
│   ├── workflows/          # Public daily-workflow router + canonical orchestration references
│   ├── planning/            # Technical planning — plan-implementation, iterate-review, finalize, feedback-classify
│   ├── pm/                  # Product management — create-feature-brief, plan-milestones, review-feature-brief, decompose-epic
│   ├── plan-review/         # Plan-reviewer lenses — architecture, backend, frontend, implementation
│   ├── review/              # Code/PR reviewer orchestration + lenses — local-review, pr-review, classify-diff, adversarial
│   ├── feedback/            # PR feedback response — triage comments, fix approved items, post replies
│   ├── pr-watch/            # Watch-and-fix loop for an open PR — CI to green + incoming comments, with escalation
│   ├── debug/               # Diagnostic umbrella — investigate-change, review-rca, check-existing-fix, CI gather/classify/fix/verify
│   ├── reflection/          # Memory capture, review/prune, failure postmortems, rule promotion
│   ├── qa/                  # QA — triage-bug, validate-fix, assess-impact, analyze/expand/execute-use-cases, file-bug
│   ├── testing/             # Test-harness work — create/update suites, review tests + test plans
│   ├── preflight/           # Pre-work environment checks — worktree setup + app-runnable env prep
│   ├── cherry-pick/         # Cherry-pick workflow — investigate, gate, plan, apply, adapt, validate, batch-sequence
│   ├── agent-setup-maintainer/ # Maintains skills, rules, adapters, and agent workflow docs
│   ├── action-gate/         # Shared proceed/stop decision helper
│   ├── implement-change/    # Focused implementation
│   ├── reporting/           # Structural rules + per-workflow summary/checkpoint templates
│   ├── metrics-emit/        # Telemetry skill — final workflow-complete event
│   ├── archive-project-file/ # Archive lifecycle skill
│   ├── shortcut/            # Shortcut REST fetch/report helpers
│   ├── superset-local/      # Superset-specific local stack + Playwright helpers
│   ├── preset-rbac-setup/   # Seed canonical RBAC test users on a staging workspace via the Manager API
│   └── workstreams/         # Post-parallel-implementation fan-in and merge sequencing
├── hooks/
│   ├── hooks.json                 # Codex plugin lifecycle-hook adapter
│   ├── prevent-project-commit.sh  # Block unsafe git flags and local workflow state commits
│   ├── pre-push-validate.sh       # Run repo-pinned ruff + targeted pytest on commits about to be pushed
│   ├── check-resources.sh         # Warn on constrained resources before tests
│   ├── check-plan-drift.sh        # Warn at turn end when PLAN.md outpaces PROJECT.md
│   ├── agent-setup-edit-reminder.sh # Remind to load agent-setup-maintainer on agent-setup edits
│   └── test-prevent-project-commit.sh # Smoke tests for the git safety hook (not a productive hook)
├── extensions/
│   └── pgm/                 # Program management (optional, install with --with-pgm)
│       ├── interfaces/       # Optional workflow manifest
│       ├── skills/pgm/       # Canonical optional Agent Skill + references
│       ├── rules/            # pgm.md (org-specific context)
│       └── install.sh        # Compatibility wrapper for the main installer
├── tests/                   # Safety, build, doctor, installer, and interface contracts
└── install-hooks.sh         # Install Claude adapter hooks (optional)
```

## Public Workflows

The `workflows` skill is the canonical interface and works with natural-language requests across Agent Skills-compatible providers. Explicit requests use `$workflows <name>`; optional PGM requests use `$pgm <name>` after opt-in installation.

The command-line interface is also stable and scriptable:

| Command | Purpose |
|---|---|
| `bin/aitk list [--with-pgm] [--details]` | List workflows and optionally include contracts/gates |
| `bin/aitk route [--with-pgm] "<request>"` | Deterministically suggest a workflow without forcing one |
| `bin/aitk build [--check] [--with-pgm]` | Generate path-resolved guidance and validate workflow manifests |
| `bin/aitk doctor [--strict] [--installed]` | Run structured repository and optional ownership-ledger checks |
| `bin/aitk checkpoint init\|validate\|advance\|reserve\|apply` | Serialize durable phases and idempotent effects; use init `--replace` only to start a new completed/stale run |
| `bin/aitk install [--with-pgm]` | Install/upgrade source links transactionally |
| `bin/aitk uninstall` | Remove only ledger-owned artifacts and managed blocks |
| `bin/aitk rollback` | Restore the exact previous lifecycle transaction once |
| `bin/aitk pgm-preflight --workflow <name>` | Fail closed before optional PGM collection |
| `bin/aitk check` | Run build drift, doctor, tests, and hook smoke tests |

See [Architecture](docs/ARCHITECTURE.md), [migration guidance](docs/MIGRATION.md),
[telemetry support](docs/TELEMETRY.md), the [10/10 completion audit](docs/COMPLETION_AUDIT.md),
and the [changelog](CHANGELOG.md).

The Python package also exposes `aitk`. Run it anywhere inside a toolkit checkout (the root is discovered from parent directories), or pass `--root <checkout>` explicitly from elsewhere.

## Migrating from Slash Commands

AI Toolkit 0.2.0 removes its generated Claude slash aliases. Workflow behavior
is unchanged: ask naturally or invoke the public router skill explicitly.

| Before 0.2.0 | 0.2.0 and later |
|---|---|
| `/fix-bug <report>` | `Fix this bug: <report>` or `$workflows fix-bug <report>` |
| `/create-feature <request>` | `Build this feature: <request>` or `$workflows create-feature <request>` |
| `/review-code` | `Review my local changes` or `$workflows review-code` |
| `/review-plan` | `Review this technical plan` or `$workflows review-plan` |
| `/fix-ci` | `Fix the failing CI checks` or `$workflows fix-ci` |
| `/test-pr <pr>` | `Test PR <pr>` or `$workflows test-pr <pr>` |
| `/watch-pr <pr>` | `Watch PR <pr>` or `$workflows watch-pr <pr>` |
| Any other core `/name [args]` | `$workflows name [args]` or its natural-language trigger |
| `/create-status-report` | `$pgm create-status-report` after `--with-pgm` installation |
| `/create-velocity-report` | `$pgm create-velocity-report` after `--with-pgm` installation |

Upgrading with `./install.sh` removes only old aliases recorded as toolkit-owned
in `~/.ai-toolkit/install-state.json`. Personal files under
`~/.claude/commands/` are left untouched. Claude's built-in `/review` remains
available; use `$workflows review-code` for the toolkit's review/fix/verify loop.
Ignored legacy `build/commands/` output may remain solely so one-level rollback
can restore a working 0.1.x installation; 0.2.0 never installs or routes it.

The `agent-setup-maintainer` skill activates automatically when you edit agent
setup files such as skills, rules, provider guidance, or hooks—see
`hooks/agent-setup-edit-reminder.sh`.

## Canonical Invocation Examples

### Code Reviews
```text
/review                     # Claude built-in review for uncommitted changes
/review --branch main       # Review changes against main
/review --commit abc123     # Review specific commit
$workflows review-code      # Toolkit review/fix/verify workflow
```

Use `/review` when you want review output only.
Use `$workflows review-code` when you want the repo-standard wrapper: review, fix, validate, and re-review until clean.

### Feature Planning
```text
$workflows create-feature "bulk edit dashboards"
$workflows create-feature sc-12345
$workflows create-feature https://github.com/owner/repo/issues/123
```

`$workflows create-feature` owns the full planning loop:
- PM planning is conditional and iterates to 8/10 when scope or milestones need it
- Developer planning iterates to 8/10 with shared reviewers from `skills/`
- The internal finalize-plan skill is the last cold-read before implementation continues automatically

### Standalone Validation
```text
$workflows run-test-plan ./docs/test-plan.md
$workflows run-test-plan sql-lab
$workflows run-test-plan https://github.com/owner/repo/pull/123
```

`$workflows run-test-plan` owns the standalone QA validation loop:
- derive or normalize a compact runnable matrix
- iterate it with `review-testplan` until it reaches 8/10 or blockers stop execution
- execute it through QA helpers and summarize findings locally

### Plan Review
```text
$workflows review-plan                # Review PLAN.md or PROJECT.md-referenced plan
$workflows review-plan --pm           # Include PM brief review
```

`$workflows review-plan` is standalone plan quality review — the same fresh-reviewer loop as `create-feature` step 4, without the full workflow.

### PR Feedback Analysis
```text
$workflows address-feedback 123       # Address review comments for PR 123
$workflows address-feedback <pr-url>  # Address review comments by URL
$workflows address-feedback 123 --draft  # Local only, don't post
```

`$workflows address-feedback` is action-first: investigate comments, fix valid issues, post replies. Its reference defines the exact authorization boundary.

### GitHub PR Reviews
```text
$workflows review-pr 123              # Review PR by number
$workflows review-pr https://github.com/owner/repo/pull/123  # Review by URL
$workflows review-pr 123 --draft      # Local only, don't post
```

## Workflow Rules

The manifest owns direct workflow loading. Skill-owned and always-on loaders are
described without workflow names so the table cannot imply manifest wiring that
does not exist.

| File | Owner / direct workflow loaders |
|------|---------------------------------|
| `rules/universal.md` | Always-on provider guidance |
| `rules/orchestration.md` | Skill-owned orchestration policy |
| `rules/context-management.md` | Always-on provider guidance |
| `rules/durable-workflows.md` | `address-feedback`, `create-feature`, `create-tests`, `fix-bug`, `fix-ci`, `review-code`, `review-code-adversarial`, `review-plan`, `review-pr`, `run-test-plan`, `test-pr`, `update-tests`, `watch-pr` |
| `rules/ci-evidence.md` | Debug and watch skill loaders |
| `rules/implementation.md` | Implementation skill loader |
| `rules/testing.md` | Testing and implementation skill loaders |
| `rules/resource-management.md` | Always-on provider guidance |
| `rules/preset-environments.md` | `run-test-plan`, `test-pr` |
| `rules/code-review.md` | Review skill loader |
| `rules/complexity-gate.md` | `address-feedback`, `create-feature`, `fix-bug`, `fix-ci`, `review-code`, `review-pr` |
| `rules/review-gate.md` | Review and workflow reference loaders |
| `rules/scoring.md` | Review and planning skill loaders |
| `rules/severity.md` | Review, planning, and QA skill loaders |
| `rules/stop-rules.md` | `review-plan` |
| `rules/shortcut-api.md` | Shortcut skill loader |
| `rules/input-detection.md` | `create-feature`, `fix-bug`, `run-test-plan`, `test-pr` |
| `rules/model-assignment.md` | Routed worker contract |
| `rules/rule-maintenance.md` | `reflect propose-rule`, rule editing |

## Hooks (optional)

Hooks enforce toolkit rules at runtime. The shell guards are provider-neutral; only their registration is provider-specific.

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

Codex hooks ship in the plugin at `hooks/hooks.json`. After enabling the plugin, review and trust them through `/hooks`; Codex deliberately requires trust again when a hook definition changes. A source-linked `install.sh` install provides skills and guidance but does not silently modify personal Codex hook configuration.

## Updating

After pulling updates, re-run the transactional installer and verify its ledger:

```bash
cd ~/opt/code/ai-toolkit
git pull
./install.sh
bin/aitk doctor --installed --strict
```

## Customization

Edit files directly in this repo. Skills take effect through source links;
provider guidance needs a rebuild because its portable paths are resolved:

- **Add a workflow**: Add its canonical reference under `skills/workflows/references/`, register it in `interfaces/workflows.json`, then run `bin/aitk build`
- **Modify rules**: Edit files in `rules/`
- **Add new rules**: Add `.md` files to `rules/`, re-run `./install.sh`
- **Refresh adapters after edits**: Run `bin/aitk build`, then re-run `./install.sh` to refresh the
  managed guidance block. A second unchanged run is a
  no-op and preserves all unrelated configuration.

## Environment Variables

Some MCP servers require tokens. Set these in your shell profile:

```bash
export GITHUB_TOKEN="your-github-token"
export OPENAI_API_KEY="your-openai-key"  # For Codex CLI
```

## Uninstall and Rollback

Lifecycle state and the one available exact backup live under
`~/.ai-toolkit/`. Use the supported APIs rather than deleting links manually:

```bash
bin/aitk uninstall
bin/aitk rollback
```

Uninstall removes only matching ledger-owned links and managed guidance blocks.
Rollback refuses drift or a corrupt/missing backup and can be applied once.

## How It Works

```
User: "build bulk dashboard editing" (or `$workflows create-feature ...`)

AI Toolkit:
1. Routes to the provider-neutral `workflows` skill
2. Loads only `skills/workflows/references/create-feature.md`
3. Loads narrower PM, planning, implementation, QA, and review skills as needed
4. Uses the provider adapter for tool-specific invocation details
5. Persists resumable state and applies the same gates on every provider
```

**Skills** = canonical behavior. **Adapters** = provider syntax. **`aitk`** = deterministic build and validation.

## Extensions

Extensions add domain-specific skills, manifests, and rules. They are not installed by default.

| Extension | Purpose | Install |
|-----------|---------|---------|
| `extensions/pgm/` | Program management reports (status, velocity) | `./install.sh --with-pgm` |
