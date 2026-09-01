# AI Toolkit

A provider-portable toolkit for repeatable AI-assisted software delivery. Canonical workflows live in Agent Skills and run through natural-language routing or explicit skill invocation.

## Mental Model

- **Goal skills** under `skills/goals/` are the entry point: the parent (a
  Sonnet-class control plane) classifies the request, dispatches bounded
  workers, and drives every workflow to one of `rules/gates.md`'s six
  terminal states (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED).
- **Rules** are short, always-on safety and routing constraints.
- **Skills** are the canonical provider-neutral workflows and domain procedures.
- **Interfaces** declare the stable public workflow names in `interfaces/workflows.json`.
- **Provider adapters** translate capabilities without duplicating workflow logic.
- **`aitk`** builds path-resolved guidance and turns structural drift into deterministic failures.
- **CI** runs the same `aitk check` gate on supported Python versions with SHA-pinned first-party actions.

## Model and Effort Routing

The parent session is a Sonnet-class control plane by default: it classifies
the request, owns `PROJECT.md`, dispatches bounded workers through the stable
routes below, and reviews their compact results. Heavy reasoning is always
dispatched to a worker, never done inline by the parent. Normal skills name a
route, never a volatile model ID; see `rules/model-assignment.md` for the full
policy and escalation ladder.

| Job | Route | Automatic effort | Codex | Claude |
|---|---|---|---|---|
| Implementation | `implementation` | high | Sol | Sonnet |
| Plan/code/test/PR review | `review` | high | Sol | Opus |
| Architecture, security, adversarial, final cold review | `deep-review` | xhigh | Sol | Fable |
| RCA | `rca` | high | Sol | Sonnet |
| Ambiguous or cross-system RCA | `deep-rca` | xhigh | Sol | Fable |
| Read-only evidence and deterministic operational summaries | `operations` | high | Sol | Sonnet |
| COMPLEX-only durable plan/investigation artifact | `planning` | high | Sol | Opus |

The route, not the model family, sets each boundary's authority: Sonnet may
edit files and run tests on `implementation`/`rca`, but stays read-only on
`operations`. Sonnet never reviews or gate-decides its own output — every
result is graded by an independent `review`/`deep-review` pass: the native
`review-worker` (Opus) / `deep-review-worker` (Fable) on Claude (the ratified
"go native" decision, see `docs/MIGRATION.md`), or Codex SOL when the
provider is Codex, which has no native roster. Routing never selects max or
falls back to a weaker model or effort.

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

The repository root is also a validated Codex plugin package (`.codex-plugin/plugin.json`) with bundled core skills and lifecycle hooks — use `install.sh` for source-linked local development, the plugin form when publishing through a marketplace. PGM stays source-linked-only in 0.2.0 (Codex plugin manifests expose one `skills/` tree; see `interfaces/support.json`). Codex supports both [Agent Skills locations](https://learn.chatgpt.com/docs/customization/skills) and [plugin distribution](https://learn.chatgpt.com/docs/build-plugins).

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
│   ├── gates.md            # Six-state gate contract (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED)
│   ├── specialist-handoff.md # Specialist dispatch input/output field contract
│   ├── severity.md         # Finding severity levels
│   ├── shortcut-api.md     # Shortcut REST API routing hint
│   ├── input-detection.md  # Route ticket/issue inputs to Shortcut or GitHub
│   └── cross-cutting.md    # Catch-all for principles that don't fit one existing rule file
├── skills/                  # Canonical Agent Skills; references load lazily (see skills/README.md for anatomy)
│   ├── workflows/          # Compatibility shim over interfaces/workflows.json; utility references (checkpoint, start, metrics, create-pr, ...) still live here
│   ├── planning/            # Technical planning — plan-implementation, decompose-work, plan-phase, finalize, feedback-classify
│   ├── review/              # Code/plan reviewer orchestration — local-review, pr-review, classify-diff, adversarial, architecture/backend/frontend
│   ├── feedback/            # PR feedback response — triage comments, fix approved items, post replies
│   ├── debug/               # Diagnostic umbrella — investigate-change, review-rca, check-existing-fix, CI gather/classify/fix/verify
│   ├── qa/                  # QA — triage-bug, validate-fix, assess-impact, analyze/expand/execute-use-cases, file-bug
│   ├── testing/             # Test-harness work — create/update suites, review tests + test plans
│   ├── preflight/           # Pre-work environment checks — worktree setup + app-runnable env prep
│   ├── pr-watch/            # PR-watch iteration/routing/stop contract — polls CI/comments, routes to fix-ci/address-feedback
│   ├── goals/                # Natural-language goal skills — fix-bug, create-feature, fix-ci, code-review, address-feedback, test-pr, cherry-pick, refactor, watch-pr, release-prep
│   ├── agent-setup-maintainer/ # Maintains skills, rules, adapters, and agent workflow docs
│   ├── implement-change/    # Focused implementation
│   ├── reporting/           # Structural rules + per-workflow summary/checkpoint templates
│   ├── metrics-emit/        # Telemetry skill — final workflow-complete event
│   ├── reflection/          # Review gate-escalation telemetry, propose rule strengthening
│   ├── archive-project-file/ # Archive lifecycle skill
│   ├── shortcut/            # Shortcut REST fetch/report helpers
│   ├── superset-local/      # Superset-specific local stack + Playwright helpers
│   └── verification-loop/   # Shared PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED contract every goal skill drives through
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

Natural-language requests route directly to the matching goal skill under `skills/goals/` (`fix-bug`, `create-feature`, `code-review`, `fix-ci`, `cherry-pick`, `address-feedback`, `test-pr`, `watch-pr`, `refactor`, `release-prep`) — each one classifies the request, dispatches the right workers, and drives `skills/verification-loop` to a terminal state. The `workflows` skill is now a compatibility shim: every entry in `interfaces/workflows.json` still resolves through `$workflows <name>`, and a handful of utility references (checkpoint, start, metrics, create-pr, and similar) live only there, but workflow behavior itself lives in the goal skill, not in this router. Optional PGM requests use `$pgm <name>` after opt-in installation.

The command-line interface is also stable and scriptable:

| Command | Purpose |
|---|---|
| `bin/aitk list [--with-pgm] [--details]` | List workflows and optionally include contracts/gates |
| `bin/aitk route [--with-pgm] "<request>"` | Deterministically suggest a workflow without forcing one |
| `bin/aitk build [--check] [--with-pgm]` | Generate path-resolved guidance and validate workflow manifests |
| `bin/aitk doctor [--strict] [--installed]` | Run structured repository and optional ownership-ledger checks |
| `bin/aitk model-route <route> --provider <codex\|claude>` | Resolve a stable worker route to its pinned model and effort |
| `bin/aitk model-run <route> --provider <p> --boundary <b> --prompt-file <f>` | Run one fail-closed worker with pinned model and effort, no downgrade |
| `bin/aitk checkpoint init\|validate\|advance\|reserve\|apply\|accept-rca\|accept-decomposition\|accept-phase-plan\|record-evidence\|record-reclassification` | Serialize durable phases, idempotent effects, and accepted-artifact/evidence/reclassification references; use init `--replace` only to start a new completed/stale run |
| `bin/aitk project-state [--file <path>]` | Read the v2 routing snapshot from PROJECT.md without loading history |
| `bin/aitk routing-state set --complexity <c> --confidence <n> --reason <r>` | Record the complexity-gate classification snapshot |
| `bin/aitk gate-state set --gate <g> --state <s> --reason <r> --count <n> [--kind mechanical\|reasoning]` | Record a gate's PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED history |
| `bin/aitk evals-run --family <name> [--live]` | Run one `evals/` fixture family through its checker; `--live` uses the routed Sonnet transport |
| `bin/aitk install [--with-pgm]` | Install/upgrade source links transactionally |
| `bin/aitk uninstall` | Remove only ledger-owned artifacts and managed blocks |
| `bin/aitk rollback` | Restore the exact previous lifecycle transaction once |
| `bin/aitk pgm-preflight --workflow <name>` | Fail closed before optional PGM collection |
| `bin/aitk check` | Run build drift, doctor, tests, and hook smoke tests |

See [Architecture](docs/ARCHITECTURE.md), [migration guidance](docs/MIGRATION.md),
[telemetry support](docs/TELEMETRY.md), the [completion audit](docs/COMPLETION_AUDIT.md),
and the [changelog](CHANGELOG.md).

The Python package also exposes `aitk`. Run it anywhere inside a toolkit checkout (the root is discovered from parent directories), or pass `--root <checkout>` explicitly from elsewhere.

## Migrating from Slash Commands

AI Toolkit 0.2.0 removed its generated Claude slash aliases in favor of
natural-language requests and goal skills; 0.3.0 moved workflow behavior into
`skills/goals/` and shrank `skills/workflows/` to a compatibility shim. Full
before/after tables, the v1→v2 vocabulary mapping, and the "go native" decision
live in [migration guidance](docs/MIGRATION.md), not duplicated here.

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
Build this feature: bulk edit dashboards
$workflows create-feature "bulk edit dashboards"
$workflows create-feature sc-12345
$workflows create-feature https://github.com/owner/repo/issues/123
```

Natural language routes directly to `skills/goals/create-feature`; `$workflows create-feature` is the stable alias. It classifies the request's complexity (`rules/complexity-gate.md`: TRIVIAL/STANDARD/COMPLEX) and size (`S`/`M`/`L`/`XL`, `aitk/size_axis.py`), derives an execution shape from both, then implements via whichever path that shape selects:
- `SINGLE_PHASE` (the common case for `S`/`M` work): a Trivial fast path implements inline with no subagent spawn, or a Standard/Complex path dispatches `implementation-worker` (and `test-worker` when needed), verifies through `skills/verification-loop`, then reviews through `skills/review/references/sol-review.md`
- `BATCHED` (repetitive/mechanical `L`/`XL` work): the same per-slice implement/verify/review loop repeated over waves or items, plus one final aggregate verification
- `MULTI_PHASE` (`L`/`XL` work with distinct, dependent capabilities): `skills/planning/references/decompose-work.md` runs once, then `plan-phase.md` plans each phase just-in-time before it implements

Every path drives to a `rules/gates.md` PASS before completion is recorded on `PROJECT.md`.

### Standalone Validation
```text
$workflows run-test-plan ./docs/test-plan.md
$workflows run-test-plan sql-lab
$workflows run-test-plan https://github.com/owner/repo/pull/123
```

`$workflows run-test-plan` owns the standalone QA validation loop:
- derive or normalize a compact runnable matrix
- iterate it with `review-testplan` until it reaches `PASS` under `rules/gates.md`'s six-state gate contract, or blockers stop execution
- execute it through QA helpers and summarize findings locally

### Plan Review
```text
$workflows review-plan                # Review PLAN.md or PROJECT.md-referenced plan
```

`$workflows review-plan` is standalone plan quality review, without a full `create-feature` run: fresh reviewer subagents (architecture, implementation-feasibility, test-plan, and conditionally frontend/backend) iterate `PLAN.md` against `rules/gates.md`'s six-state gate contract, then a fresh cold read gates completion.

### PR Feedback Analysis
```text
$workflows address-feedback 123       # Address review comments for PR 123
$workflows address-feedback <pr-url>  # Address review comments by URL
$workflows address-feedback 123 --draft  # Local only, don't post
```

The `address-feedback` goal skill (`$workflows address-feedback` is its stable alias) is action-first: investigate comments, fix valid issues, post replies. Its `SKILL.md` defines the exact authorization boundary.

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
| `rules/context-management.md` | Always-on provider guidance; `cherry-pick` |
| `rules/durable-workflows.md` | `address-feedback`, `cherry-pick`, `create-feature`, `create-tests`, `fix-bug`, `fix-ci`, `refactor`, `release-prep`, `review-code`, `review-code-adversarial`, `review-plan`, `review-pr`, `run-test-plan`, `test-pr`, `update-tests`, `watch-pr` |
| `rules/ci-evidence.md` | Debug skill loaders |
| `rules/implementation.md` | Implementation skill loader |
| `rules/testing.md` | Testing and implementation skill loaders |
| `rules/resource-management.md` | Always-on provider guidance |
| `rules/preset-environments.md` | `run-test-plan`, `test-pr`, `release-prep`, `watch-pr` |
| `rules/code-review.md` | Review skill loader |
| `rules/complexity-gate.md` | `address-feedback`, `cherry-pick`, `create-feature`, `fix-bug`, `fix-ci`, `refactor`, `review-code`, `review-pr` |
| `rules/gates.md` | Six-state gate contract (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED); `review-plan`; also loaded directly by every `skills/goals/*` skill and `skills/review`, independent of this manifest's per-workflow rule imports |
| `rules/specialist-handoff.md` | Specialist dispatch input/output field contract; authoritative for every goal-skill dispatch and every native worker under `agents/claude/` |
| `rules/severity.md` | Review, planning, and QA skill loaders |
| `rules/shortcut-api.md` | Shortcut skill loader |
| `rules/input-detection.md` | `create-feature`, `fix-bug`, `run-test-plan`, `test-pr` |
| `rules/model-assignment.md` | Routed worker contract |
| `rules/rule-maintenance.md` | Ad hoc rule editing |
| `rules/cross-cutting.md` | Skill-owned loader |

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

- **Add a workflow**: Most new behavior is a new (or extended) goal skill, not
  a router entry — add `skills/goals/<name>/`, register it in
  `interfaces/workflows.json` with `"reference"` pointing at that skill's
  `SKILL.md`, and add matching entries in `interfaces/contracts.json`/
  `skills.json`, then run `bin/aitk build`. A handful of utility references
  (checkpoint, start, metrics, create-pr) are the exception, have no
  `reference` override, and stay under `skills/workflows/references/`; see
  `docs/ARCHITECTURE.md`'s "Adding a workflow" for the full sequence.
- **Modify rules**: Edit files in `rules/`
- **Add new rules**: Add `.md` files to `rules/`, re-run `./install.sh`
- **Refresh adapters after edits**: Run `bin/aitk build`, then re-run `./install.sh` to refresh the
  managed guidance block. A second unchanged run is a
  no-op and preserves all unrelated configuration.

Recommended Claude Code settings for this toolkit are documented in
`rules/context-management.md`.

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
1. Routes directly to the matching goal skill (`skills/goals/create-feature`);
   `$workflows create-feature` is a stable alias, not the canonical location
2. The parent (Sonnet-class control plane) classifies complexity/size, picks
   the smallest execution shape, and dispatches bounded workers through the
   stable routes in `interfaces/model-routing.json`
3. Drives `skills/verification-loop` to a six-state terminal
   (PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED); only
   USER_DECISION/BLOCKED surface to the user
4. Persists resumable state on `PROJECT.md` and applies the same gates on
   every provider
```

**Skills** = canonical behavior. **Adapters** = provider syntax. **`aitk`** = deterministic build and validation.

## Extensions

Extensions add domain-specific skills, manifests, and rules. They are not installed by default.

| Extension | Purpose | Install |
|-----------|---------|---------|
| `extensions/pgm/` | Program management reports (status, velocity) | `./install.sh --with-pgm` |
