# Orchestration

## Goal Loop

The parent session is the orchestrator and runs on the workhorse family named in
`interfaces/model-routing.json` (`policy.orchestrator`: Sonnet on Claude, Sol on
Codex). A goal workflow is a thin state machine: read the routing snapshot in
`PROJECT.md`, evaluate the current gate, choose the next bounded capability,
record the handoff, repeat until every required gate is `PASS`.

The parent owns: classification, the routing snapshot, gates, durable state,
authorization boundaries, user decisions, and final synthesis. It does trivial
and tightly coupled work inline. Everything verbose or substantial runs in a
fresh worker and comes back as a compact handoff.

## Execution Isolation

| Mechanism | Use for | Avoid when |
|---|---|---|
| Inline in the parent | TRIVIAL work, classification, small edits, gate decisions | The step will load large logs, diffs, or many files |
| Native fresh subagent (toolkit roster) | Substantial implementation, noisy investigation, test authoring, COMPLEX planning | The task is tiny or needs the parent's live context |
| Forked one-shot leaf skill | Verification, impact scan, existing-fix scan: the skill body is the whole task | The step must own durable state |
| Routed specialist (`model-run`) | Independent review, RCA validation, plan validation: a different model and provider | Mechanical implementation or routine test editing |
| Full-history fork | Rare side investigation that needs most of the live conversation | Normal phase boundaries |

Workers are the phase boundary. A worker starts fresh, does one bounded phase,
returns a handoff, and ends; its tool history never enters the parent. Cap
nesting at the goal skill, one worker layer, and one exceptional specialist
child. Never review your own work: review and validation always run in a fresh
context, preferably on the other provider.

Spawn a worker only when it buys isolation, parallelism, or a different model.
Every spawn costs orchestrator turns; a sequential, bounded, short-result step
stays inline.

## Batch Rules

- Start with one unit unless independence is already proven; batch two or
  three only with disjoint ownership and clear dependencies.
- Shared APIs, migrations, auth, routing, state models, generated artifacts, and
  cross-cutting contracts are single-unit work.
- Each worker gets only its unit, the relevant excerpt, entrance and exit
  criteria, the acceptance check, and the handoff shape.
- After each wave: collect handoffs, update durable state, run the gate, then
  decide the next wave. Never start a wave while one has a failed gate, a merge
  conflict, or an open user decision.

## Context Loading

The parent loads the rules it evaluates (complexity gate, gates, orchestration,
input detection). Workers receive their domain rules inline through the handoff
or the route closure. Do not load a rule in both places unless the parent must
grade the returned handoff against it.
