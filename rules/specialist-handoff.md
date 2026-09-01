# Specialist Handoff

A shared contract for how the orchestrator hands a bounded task to any
specialist worker — a native Claude subagent or a Codex SOL specialist — and
for what that worker returns. This fixes one input shape and one output shape
so every specialist call can be authored and consumed the same way, whether
dispatched via native Task-tool routing or through Codex's `model-run`
boundary.

**Status: authoritative.** This is the handoff contract every goal skill
(`skills/goals/fix-bug`, `cherry-pick`, and the rest) and every native worker
(`agents/claude/{implementation-worker,debug-worker,test-worker,planner,
review-worker,deep-review-worker}.md`) actually dispatch and return against —
not an aspirational future shape. `skills/implement-change/SKILL.md`'s
`## Implementation Handoff` block is this contract's concrete instance for
the `implement` phase.

## Input Contract (what the orchestrator hands to a specialist)

Every dispatch supplies exactly these fields:

- **Goal**: the one-sentence outcome the specialist must produce.
- **Phase**: which workflow phase this call belongs to (investigate, plan,
  implement, review, rca, verify) — lets the specialist and the reviewing
  gate agree on what "done" means.
- **Scope**: the explicit boundary — files, directories, or a slice
  definition the specialist must stay inside. Anything outside scope is out
  of bounds even if related.
- **Evidence pointer**: a path (`PROJECT.md`, `PLAN.md`, a diff, a log
  excerpt) the specialist reads for context, never a transcript dump of the
  orchestrator's own conversation. If the specialist needs more than a
  file's current content, name the exact excerpt or command that produces it.
- **Constraints**: anything the specialist must not do — no commits, no scope
  widening, no unauthorized effects. Permission mode and disallowed tools are
  already enforced by the route in `rules/model-assignment.md`; restate only
  task-specific constraints here.
- **Exit criteria**: the condition that ends this call, stated so the
  specialist can self-check before returning.
- **Author identity** (review/deep-review phases only): the worker identity
  that produced the change under review (e.g. `implementation-worker`), so
  the reviewing specialist can assert it is never reviewing its own output —
  `aitk.gates.assert_independent_verification` is the machine-checkable
  slice of that rule. Omit for phases with no prior author to check against.

## Output Contract (what a specialist returns)

- **Status**: the `rules/gates.md` vocabulary (`PASS`/`RETRY`/`ESCALATE`/
  `BLOCKED`/`USER_DECISION`/`RECLASSIFY`) when the call is gate-checked.
- **Evidence summary**: compact, not a raw log or transcript — the
  orchestrator must be able to act on it without re-reading everything the
  specialist saw.
- **Changed artifacts**: files touched, if any. Read-only specialists (review,
  rca) return none.
- **Blockers**: anything preventing progress, or "none."
- **Residual risk / unverified areas**: named gaps, not silence.
- **Next-action implication**: what the orchestrator should do with this
  result — advance the phase, retry, escalate, or ask the user.

## No Transcript Dumps

Neither direction of this contract carries a full conversation transcript.
The input side points at durable artifacts rather than replaying prior turns;
the output side is the compact handoff shape above, not raw tool output or a
chat log. `rules/orchestration.md`'s Subagent Context Loading section already
establishes this discipline for rule loading — this rule extends it to the
handoff payload itself.

## Scope

This rule defines the input/output field contract only. It does not decide
which specialist a given phase routes to (`rules/model-assignment.md`), when
a specialist is warranted versus inline work (`rules/orchestration.md`'s
Inline-First Principle), or how a gate outcome is persisted (`rules/gates.md`,
`aitk gate-state`).
