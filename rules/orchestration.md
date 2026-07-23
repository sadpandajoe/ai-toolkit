# Orchestration Principles

## Primary Orchestrator Model

The active coding agent is the primary orchestrator: planning, investigation, complex reasoning, verification, durable state, and final synthesis. Secondary tools, CLIs, models, or subagents are optional delegatees for bounded, well-specified tasks when available.

| Role | Owner | Examples |
|------|-------|---------|
| **Orchestrator** | Active coding agent | Planning, architecture, RCA, multi-file refactors, security-sensitive code |
| **Delegatee** (optional) | Secondary tool/model/CLI | Single-file implementations, boilerplate, mechanical transforms, test generation from spec |
| **Internal workers** | Subagents/workers | Exploration, planning, research |
| **Domain reviewers** | Skill subagents | Architecture, implementation, testing, frontend, backend perspectives |

## Model Routes And Effort

The active parent session is the orchestrator and keeps the user's selected
workhorse configuration. Every spawned model worker uses a stable route from
`rules/model-assignment.md`; the route resolver supplies the exact current
selector, effort, permission boundary, and output contract.

Use the normal `implementation`, `review`, or `rca` route for bounded work. Use
`deep-review` for architecture, security, adversarial analysis, and meaningful
final cold reads. Use `deep-rca` when evidence is ambiguous, intermittent,
history-dependent, or crosses systems. Use `operations` only for its narrow,
non-development allowlist. Automatic implementation stays on the normal
Sol/Opus workhorse route; Fable remains a read-only deep advisor.

High is the automatic baseline; xhigh is reserved for deep routes. Automatic
dispatch never selects max and never falls back to a weaker model or effort.
Resolve the toolkit/package root from the installed skill. Resolve with
`<toolkit-root>/bin/aitk model-route --boundary <marker-id>`, then launch with
`<toolkit-root>/bin/aitk model-run --boundary <marker-id>`.

**Cherry-pick routing**: the cherry-pick gate classifies difficulty (TRIVIAL vs
NON-TRIVIAL) and selects `review` or `deep-review` for the mandatory post-apply
scope audit. Planning, application, adaptation, and correctness validation stay
with the main thread. See `skills/cherry-pick/references/gate.md` for the route
table; exact effort values remain manifest-owned.

The orchestrator may run on any user-selected model that satisfies the user's
workhorse policy. The stable routes apply to **subagents/workers** spawned from
it and cannot retroactively change the parent session.

## Inline-First Principle

Every subagent spawn costs orchestrator messages. On subscription plans, this directly reduces how much work fits in a session. Before spawning a subagent, ask: **does this task need a separate agent, or can the orchestrator do it inline?**

Spawn a subagent when:
- Parallelism provides a clear wall-clock win (multiple independent investigation lanes)
- Isolation matters (reviewer should not see implementation context, cold read needs fresh eyes)
- The work is a **review** — never review your own work; always use a separate subagent for code and plan reviews

Do it inline when:
- The work is sequential anyway (classification, single-file investigation, planning a scoped fix)
- The orchestrator already has the relevant context loaded
- The task is bounded and the result is short (triage, RCA for a single failure mode)

When the complexity gate classifies work as MODERATE, default to inline for
scoping, investigation, and planning, but still use `fresh_subagent` for the
required reviewer. When STANDARD, follow the workflow's declared capability
steps.

## Long-Running Workflow Pattern

When a workflow may process many units, inspect large logs, or run across multiple phases, the main thread should stay as a thin orchestrator rather than becoming the durable memory for every raw detail.

- **Main thread owns** ordering, dependency tracking, user decisions, checkpoint boundaries, and final synthesis.
- **Durable state lives in files**: use `PROJECT.md`, `PLAN.md`, or a workflow-specific local manifest when chat history would otherwise become the state store.
- **Subagents own bounded expensive context**: each receives only the unit, wave, or lane it needs plus the output contract.
- **Subagents return compact handoffs**: status, evidence summary, blockers, verification, residual risk, and next-action implications. Do not return full logs or diffs unless blocked.
- **The main thread updates durable state after every unit or wave** before starting the next one.
- **Checkpoint between waves/phases** per `rules/context-management.md`. For STANDARD or expensive work, phase resets are proactive: apply `context_reset` after durable artifacts are updated, not only when context or cost is near a limit.

Use workflow-specific manifests when the work has a natural table of units, for
example large cherry-pick trains, multi-failure CI fixes, or batch PR reviews.
Keep those files local-only unless the workflow explicitly says otherwise.

## Subagent Batch Rules

Use these rules whenever a workflow delegates implementation, investigation lanes, review batches, cherry-pick waves, or CI failure groups.

- Start with one unit unless the plan already proves independence.
- Batch 2-3 units only when ownership is disjoint and dependencies are clear.
- Use a single unit when work touches shared APIs, migrations, auth, routing, state models, generated artifacts, or cross-cutting contracts.
- Each subagent gets only the unit scope, relevant context excerpt, entrance criteria, exit criteria, expected validation, and handoff format.
- After each wave, collect compact handoffs, update durable state, run any required fan-in or review gate, then decide the next wave.
- Do not start the next wave while the current wave has failed acceptance, merge conflicts, unresolved review findings, or an open user decision.

## Subagent Context Loading

Workers load their own domain rules; public workflow references should not
eagerly import rules used only by workers.

- **Main thread imports**: rules the main thread directly evaluates (complexity gate, input routing, orchestration, planning)
- **Subagent reads**: domain rules the subagent applies (code-review, testing, implementation, investigation, review-gate, stop-rules, shortcut-api)
- **Skill files reference rules by path**: e.g., "Read and apply `rules/review-gate.md`"
- **Workflows tell workers which files to read**: resolve the rule through the
  manifest/root mapping and include its content or stable path in the bounded handoff

Avoid redundantly loading the same rule in both contexts unless the main thread must evaluate a returned gate or handoff against that rule.
