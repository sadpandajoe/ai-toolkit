# Orchestration Principles

## The Parent Session Is A Control Plane

The active parent session is a Sonnet-class control plane by default: it
classifies incoming work (`rules/complexity-gate.md`'s TRIVIAL/STANDARD/
COMPLEX tier crossed with the S/M/L/XL size axis, deriving execution shape
SINGLE_PHASE/BATCHED/MULTI_PHASE — see `skills/goals/create-feature/
SKILL.md`'s Size Gate step), owns `PROJECT.md`/`PLAN.md` as the only writer,
dispatches bounded workers for phases needing heavy reasoning, and reviews
their compact returned results. Route table, effort ladder, and per-provider
dispatch transport live in `rules/model-assignment.md`, not here.

## Goal Skills Own The Loop

`skills/goals/*` (`fix-bug`, `create-feature`, `code-review`, `fix-ci`,
`address-feedback`, `test-pr`, `watch-pr`, `refactor`, `release-prep`,
`cherry-pick`, …) each own their workflow end to end — classification,
branching by tier, dispatch, gates, completion. This file states the
cross-cutting principles those skills all follow; it is not itself an entry
point and does not replace a goal skill's own steps.

**Cherry-pick's classification is the same gate, not a special case.**
`skills/goals/cherry-pick` classifies each change against the identical
TRIVIAL/STANDARD/COMPLEX vocabulary from `rules/complexity-gate.md` (its own
`references/gate.md` supplies the difficulty-signal table cherry-picks need,
same shape as any other goal skill's signal table) and uses that
classification to select the mandatory post-apply scope-audit route: `review`
for TRIVIAL/STANDARD, `deep-review` for COMPLEX. Planning, application,
conflict adaptation, and correctness validation stay on the parent thread
regardless of tier.

## Inline-First Principle

Every subagent spawn costs orchestrator messages and, on subscription plans,
directly reduces how much work fits in a session. Before spawning a
subagent, ask: **does this task need a separate agent, or can the parent do
it inline?**

Stay inline for:
- Classification (`rules/complexity-gate.md`'s gate itself) and all
  `PROJECT.md`/`PLAN.md` state writes — these are parent-only regardless of
  tier.
- The entire TRIVIAL fast-path implementation — per
  `rules/complexity-gate.md`'s Trivial Fast-Path, zero subagent spawns for
  the implementation itself.

Dispatch a bounded worker for:
- Any phase that requires heavy reasoning — investigation, RCA, planning,
  non-trivial implementation, review — per `rules/model-assignment.md`'s
  route table. The parent is a control plane; it hands these phases to the
  matching route rather than reasoning through them itself.
- **Every review** — never review your own work. A fresh reviewer subagent
  is the floor at every tier, TRIVIAL included, whenever the workflow's
  product involves reviewing changed code.
- Parallel investigation lanes, when wall-clock parallelism gives a clear
  win and the units are genuinely independent.

STANDARD and COMPLEX work follow their goal skill's declared dispatch steps;
this section states the default, not a per-workflow override.

## Worker Isolation And Bounded Handoffs

Every dispatch to a worker follows `rules/specialist-handoff.md`'s input/
output field contract — Goal, Phase, Scope, Evidence pointer, Constraints,
Exit criteria in; Status, Evidence summary, Changed artifacts, Blockers,
Residual risk, Next-action implication out. Workers never see the parent's
raw conversation transcript and never write `PROJECT.md`/`PLAN.md` — only the
parent does, after folding a worker's compact result back in. See
`rules/context-management.md`'s Workers as Phase Isolation for why dispatch,
not an explicit reset, is the isolation mechanism, and its Save and Continue
Protocol for what the parent checkpoints after each handoff.

## Max Nesting Depth

Spawn depth stays at one level by default: the parent dispatches a worker,
that worker returns rather than dispatching further workers of its own.
`rules/resource-management.md` owns this rule and its narrow exception (a
calling procedure that explicitly names a second dispatch layer); this file
does not restate the exception list.

## How Gates Route

Every checkpoint a goal skill or worker hits — verification, review, RCA
validation, plan review — emits `rules/gates.md`'s six-state block and
follows its repeat-failure counting rule. `RETRY`/`ESCALATE` are autonomous;
only `USER_DECISION`/`BLOCKED` surface to the user; `RECLASSIFY` sends the
workflow back through the Complexity Gate. This file does not restate
`rules/gates.md`'s vocabulary or counting rule — read it there.

## Subagent Batch Rules

Applies whenever a goal skill dispatches multiple units — cherry-pick waves,
CI failure groups, batch PR reviews, or a `BATCHED` shape's per-item loop:

- Start with one unit unless the plan already proves independence; batch 2-3
  only when ownership is disjoint and dependencies are clear. Use a single
  unit when work touches shared APIs, migrations, auth, routing, state
  models, or cross-cutting contracts.
- Each unit's dispatch carries only that unit's scope and the
  `rules/specialist-handoff.md` fields — never the whole batch's context.
- After each wave: collect compact handoffs, update `PROJECT.md`, run any
  required fan-in or review gate, then decide the next wave. Do not start
  the next wave while the current one has failed acceptance, merge
  conflicts, unresolved review findings, or an open `USER_DECISION`.

## Subagent Context Loading

Workers load their own domain rules; the parent should not eagerly import
rules used only by workers. The parent imports what it directly evaluates —
the complexity gate, gates, orchestration, and (for COMPLEX work) planning.
Workers read the domain rules they apply — code-review, testing,
implementation, investigation, gates — resolved via their own frontmatter or
the dispatching skill's instructions. Goal skills reference rules by path
(e.g. "Read and apply `rules/gates.md`") rather than inlining their content,
and avoid loading the same rule in both contexts unless the parent must
evaluate a returned gate or handoff against it directly.
