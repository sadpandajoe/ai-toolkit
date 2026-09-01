# Architecture

AI Toolkit separates stable workflow behavior from provider syntax. Sonnet is
the control plane: it classifies the request, owns `PROJECT.md`, and drives
the shared verification loop to evidence-backed completion. Opus is a bounded
planning specialist invoked only for `COMPLEX` decomposition and phase
planning. RCA, plan validation, and code review always run independent of the
context that produced the artifact under review — on the Claude provider that
independent check is the native `review-worker` (Opus) / `deep-review-worker`
(Fable) roster (the ratified "go native" decision; see `PLAN.md`'s "Open
decisions for the user"); Codex SOL is the independent verifier only when the
active provider is Codex, which has no native worker roster of its own.
Skills own workflows; agents exist for context isolation; rules hold
only short cross-cutting constraints. `skills/verification-loop` is the one
shared PASS/RETRY/ESCALATE/RECLASSIFY/USER_DECISION/BLOCKED contract every
goal workflow drives through. `PROJECT.md` is durable state; chat history is
disposable.

You say what you want. The correct goal skill routes it, Sonnet classifies
complexity and size, the toolkit chooses the smallest successful execution
shape and model tier, fresh workers keep context bounded, `verification-loop`
drives the goal to evidence-backed completion, and `PROJECT.md` makes the
whole process resumable.

## Repository shape

```text
skills/
  goals/
    fix-bug/ create-feature/ code-review/ fix-ci/ cherry-pick/
    address-feedback/ test-pr/ watch-pr/ refactor/ release-prep/
  verification-loop/
  debug/ planning/ testing/ qa/ review/ preflight/
  reflection/ shortcut/ superset-local/ reporting/ ...
  workflows/            # compatibility shim only — see "Adding a workflow"

agents/
  claude/
    planner.md
    implementation-worker.md
    debug-worker.md
    test-worker.md
    review-worker.md
    deep-review-worker.md
  codex/
    rca.md
    plan-validator.md
    reviewer.md

rules/
  universal.md orchestration.md model-assignment.md complexity-gate.md
  context-management.md durable-workflows.md implementation.md
  code-review.md testing.md ci-evidence.md severity.md
  resource-management.md rule-maintenance.md input-detection.md
  shortcut-api.md preset-environments.md gates.md cross-cutting.md
  specialist-handoff.md
  scoring.md stop-rules.md review-gate.md   # kept for plan-domain reviewers,
                                             # see rules/gates.md's
                                             # "Permanently out of scope" note

evals/   # model judgment (skill routing, classification, escalation, ...)
tests/   # deterministic guarantees (state parsing, gate transitions, ...)
```

Two differences from the source spec's file layout are deliberate, not drift:

- Agents live at `agents/claude/*.md` and `agents/codex/*.md`, not
  `.claude/agents/*.md`. The installer symlinks them into place; the
  source-linked location is what this repo's own tooling and tests operate on.
- The Claude side has **six** native worker files, not four. Review and
  deep-review went native alongside the original four (planner,
  implementation-worker, debug-worker, test-worker) because
  `interfaces/model-routing.json` pins them to different models, so they
  needed two files. This is coverage beyond the spec's minimum, not a gap.

`skills/goals/address-feedback` (not `pr-feedback`) is an open naming
decision, not a settled deviation — see `PLAN.md`'s "Open decisions for the
user."

## Layers

1. `rules/` contains short cross-workflow constraints — the roster above.
2. `skills/goals/` is the natural-language entrypoint: each of the ten goal
   workflows in spec §7 (`address-feedback` standing in for the spec's
   `pr-feedback`) is
   a short pipeline that classifies the request, dispatches the right
   workers, and drives `skills/verification-loop` to a terminal state.
   `skills/workflows/` is a pure compatibility shim — every entry in
   `interfaces/workflows.json` names a goal skill or a utility reference; it
   is not itself where workflow behavior lives.
3. `interfaces/workflows.json` and the optional extension manifests declare
   workflow identity, owner skill, routing, rule imports, and execution class.
   `interfaces/contracts.json` v2 declares the phase graph, authorization,
   effects, idempotency, verification, reporting, and recovery behavior.
   `interfaces/skills.json`, `providers.json`, `model-routing.json`,
   `guidance.json`, and `support.json` make public discovery, provider
   capabilities, fail-closed model routing, shared always-on guidance, and the
   release matrix explicit.
4. `.codex-plugin/`, `skills/*/agents/openai.yaml`, `hooks/hooks.json`, and `config/AGENTS.md` form the Codex adapter.
5. `aitk/` and `bin/aitk` build, route, validate, transact installation, and
   serialize durable workflow checkpoints.

Optional extensions repeat the same pattern below `extensions/<name>/`: a manifest, canonical Agent Skill, and any extension-specific rules. `--with-pgm` opts the bundled PGM extension into validation, routing, and installation.

The version 0.2.0 Codex plugin packages the core `skills/` tree. PGM remains an
explicitly source-linked extension until plugin distribution supports its
separate skill root; `interfaces/support.json` makes that distribution boundary
machine-readable.

## Source-of-truth flow

```text
workflow manifest + v2 contract + canonical skill reference
                 │
       ┌─────────┴──────────┐
       │                    │
 routing/validation  checkpoint runtime
                            │
                   PROJECT.md machine block
```

Provider adapters may translate invocation syntax, tool names, planning controls, scheduling, and independent-review capabilities. They may not weaken authorization boundaries, protected state, stop conditions, verification labels, or reporting contracts.

## Model workers

Most of the roster dispatches natively, as Claude Code subagents defined
under `agents/claude/`: `planner` (Opus, `COMPLEX` decomposition and phase
planning only), `implementation-worker`, `debug-worker`, and `test-worker`
(Sonnet), plus the native independent verifiers `review-worker` (Opus) and
`deep-review-worker` (Fable) — the two files the "go native" decision added
so the `review`/`deep-review` boundaries never grade the Sonnet work that
produced them. These carry no source-linked transport — a goal skill invokes
them the same way it would any other Claude subagent, and each one is the
phase-level context reset: fresh context in, a compact handoff out.

The stricter source-linked boundary — `<toolkit-root>/bin/aitk model-route`
plus `<toolkit-root>/bin/aitk model-run` — still exists for the Codex
specialists (`agents/codex/{rca,plan-validator,reviewer}.md`, run at SOL High,
escalating to SOL XHigh only for exceptional adjudication) and for three
Claude boundaries that have not yet gotten a native worker file:
`deep-rca`, `operations`, and the review-ensemble lanes
(`config/providers/claude.md`'s `routed_subagent` binding documents the
split). `model-route` resolves the exact selector, effort, and permissions
from `interfaces/model-routing.json`; `model-run` validates the boundary,
provider CLI, and route before launching one structured worker without
downgrade or generic-worker fallback. Each boundary deterministically derives
a validated transitive inline contract closure from the shared model rule,
owner and responsibility skills, required-context dependencies, selected
review lenses, and canonical dispatch document; callers cannot substitute
arbitrary files. Codex launches from a sanitized temporary project root and
exposes the target only through `--add-dir`, while also disabling project-document discovery,
user config, hooks, MCP servers, and exec-policy rules. The toolkit guarantees
the requested CLI configuration and validates the returned envelope. Inline
SHA-256 labels identify the exact content sent for diagnostics; they are not
compared with a separately trusted expected digest. Neither supported provider
result format attests the internal serving-model identity, so provider backend
execution and substitution remain the provider's responsibility.

The review-ensemble lanes' removal is deferred, not scheduled — see
`PLAN.md`'s D2 "Corrected scope" note for the precondition. The Codex path
cannot be removed while any of these three boundaries still calls it.

The Codex plugin bundle retains `bin/`, `aitk/`, `config/`, `interfaces/`,
`rules/`, and `skills/` beneath one plugin root. Routed skills resolve that root
from their installed location; they never assume the user's product repository
contains `bin/aitk`. Isolated-plugin tests execute the resolver from an
unrelated working directory.

## Verification and state

`skills/verification-loop` is the shared contract every goal workflow drives
through: PASS, RETRY, ESCALATE, RECLASSIFY, USER_DECISION, or BLOCKED. A
worker never self-certifies its own phase — only the parent Sonnet
orchestrator updates `PROJECT.md`'s phase-transition and retry-attempt state.

Long-running workflows write human state plus one canonical
`aitk-checkpoint:v1` JSON block in `PROJECT.md`, including the v2 routing
snapshot fields (`workflow`, `complexity`, `size`, `execution_shape`,
`current_phase`, `phase_complexity`, `phase_size`, `phase_execution_shape`,
`verification_status`, `reasoning_attempts`). `bin/aitk checkpoint` owns its
serialization, legal phase transitions, generation counter, and pending/applied
effect records. A stable operation ID is reserved before an effect and applied
only after execution or reconciliation. Semantic contract changes invalidate
old checkpoints through a canonical contract digest. Effect keys are categories,
not one-shot slots: repeated pushes, posts, and review rounds append distinct
records keyed by their stable operation IDs.

Focused manifests such as `PLAN.md`, `WATCH.md`, or `CI_FIX.md` can supplement
that checkpoint when a durable architecture/decomposition artifact is useful.
All local workflow-state files are ignored by git and blocked by the safety
hook if staged. Resume uses durable files, never chat history.

## Install ownership

Source-linked installation is a transaction recorded in mode-0600
`~/.ai-toolkit/install-state.json`. The inventory is derived from the manifests
and public skill classification. Guidance is owned only inside delimiters;
links are owned by exact target/source records. Install/upgrade, uninstall, and
one-level rollback validate every ledger path before mutation, preserve user
conflicts, and restore exact bytes/modes/links on pre-commit failure. A moved
checkout is an explicit upgrade whose prior root remains recoverable.

Internal skills are packaged for resolver use but are not linked as standalone
Agent Skills. During a 0.2.0 upgrade, the lifecycle ledger removes old
toolkit-owned Claude aliases while preserving unrelated personal commands.

## Adding a workflow

Most new behavior is a new (or extended) goal skill, not a new router entry:

1. Add `skills/goals/<name>/` with its own `SKILL.md` describing the
   pipeline: classify, dispatch workers, drive `skills/verification-loop`.
2. Register the name, summary, arguments, rules, and routing triggers in
   `interfaces/workflows.json` (`skills/workflows/` picks this up as its
   shim entry — do not add router logic there).
3. Add a total v2 entry to `interfaces/contracts.json`; use the canonical
   durable runtime rule and runtime-contract section when execution is durable.
4. Classify any new skill in `interfaces/skills.json`.
5. Run `bin/aitk build` (or `--with-pgm` to validate the bundled extension).
6. Add positive and negative routing, semantic, recovery, and provider cases,
   then run `bin/aitk check`.

A handful of utility references (checkpoint, start, metrics, create-pr, and
similar) live directly under `skills/workflows/references/` rather than as
their own goal skill — these are still registered the same way, via
`interfaces/workflows.json`.

Do not add workflow logic to provider config, hooks, or the manifest.

For an optional extension, use the matching `extensions/<name>/interfaces/workflows.json` and `extensions/<name>/skills/<name>/references/` locations, then validate it with the same conformance gate.
